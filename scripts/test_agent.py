#!/usr/bin/env python3
"""
CLI tool to test the Conversational Analytics agent without the Streamlit UI.

Usage:
    # Interactive mode
    python scripts/test_agent.py

    # Single query
    python scripts/test_agent.py "What are our top 10 selling items?"

    # Run stress test questions (original mode - new conversation every 10 questions)
    python scripts/test_agent.py --stress-test

    # Run grouped stress test (one conversation per category, tests context)
    python scripts/test_agent.py --stress-test --grouped

    # Run grouped stress test with file logging
    python scripts/test_agent.py --stress-test --grouped --log

    # Limit to first N questions
    python scripts/test_agent.py --stress-test --grouped --log --limit 10

    # List available agents
    python scripts/test_agent.py --list-agents
"""

import argparse
import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.cloud import geminidataanalytics
from google.api_core import exceptions as google_exceptions

# Default project ID - can be overridden with --project
DEFAULT_PROJECT_ID = "fdsanalytics"

# ANSI colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def get_agents(client, project_id):
    """List all available agents."""
    request = geminidataanalytics.ListDataAgentsRequest(
        parent=f"projects/{project_id}/locations/global"
    )
    return list(client.list_data_agents(request=request))


def create_conversation(client, project_id, agent_name):
    """Create a new conversation with the specified agent."""
    conversation = geminidataanalytics.Conversation()
    conversation.agents = [agent_name]

    request = geminidataanalytics.CreateConversationRequest(
        parent=f"projects/{project_id}/locations/global",
        conversation=conversation,
    )
    return client.create_conversation(request=request)


def send_message(chat_client, project_id, agent_name, conversation_name, message_text):
    """Send a message to the agent and return the response."""
    user_msg = geminidataanalytics.Message(user_message={"text": message_text})
    convo_ref = geminidataanalytics.ConversationReference()
    convo_ref.conversation = conversation_name
    convo_ref.data_agent_context.data_agent = agent_name

    request = geminidataanalytics.ChatRequest(
        parent=f"projects/{project_id}/locations/global",
        messages=[user_msg],
        conversation_reference=convo_ref,
    )

    responses = []
    for message in chat_client.chat(request=request):
        responses.append(message)
    return responses


def format_response(message, verbose=False):
    """Format the agent response for CLI display."""
    output = []

    if hasattr(message, 'system_message'):
        sys_msg = message.system_message

        # Text response (the main answer)
        if hasattr(sys_msg, 'text') and sys_msg.text:
            text = sys_msg.text
            # Handle proto TextMessage
            if hasattr(text, 'text'):
                output.append(text.text)
            elif hasattr(text, 'parts') and text.parts:
                # Extract text from parts, filtering out JSON chart specs
                for part in text.parts:
                    part_text = str(part) if part else ""
                    # Skip JSON chart specifications
                    if "```json" in part_text:
                        part_text = part_text.split("```json")[0].strip()
                    # Clean up the text
                    part_text = part_text.strip().strip('"').strip("'")
                    if part_text and len(part_text) > 5:
                        output.append(f"\n{Colors.GREEN}{part_text}{Colors.ENDC}")
            else:
                text_str = str(text)
                if text_str and text_str != "text {\n}":
                    output.append(text_str)

        # Generated SQL
        if hasattr(sys_msg, 'data') and sys_msg.data:
            data = sys_msg.data
            if hasattr(data, 'generated_sql') and data.generated_sql:
                output.append(f"\n{Colors.DIM}SQL:{Colors.ENDC}")
                output.append(f"{Colors.CYAN}{data.generated_sql}{Colors.ENDC}")

        # Chart/visualization - just note it exists
        if hasattr(sys_msg, 'chart') and sys_msg.chart:
            chart = sys_msg.chart
            # Check if it has actual chart content
            chart_str = str(chart)
            if chart_str and len(chart_str) > 10:  # Has meaningful content
                output.append(f"{Colors.YELLOW}[Chart generated]{Colors.ENDC}")

        # Data table
        if hasattr(sys_msg, 'data_table') and sys_msg.data_table:
            table = sys_msg.data_table
            rows = getattr(table, 'rows', None)
            if rows:
                output.append(f"\n{Colors.DIM}Data ({len(rows)} rows):{Colors.ENDC}")
                for i, row in enumerate(rows[:10]):
                    output.append(f"  {row}")
                if len(rows) > 10:
                    output.append(f"  ... and {len(rows) - 10} more rows")

        # Verbose: show raw structure for debugging
        if verbose and not output:
            output.append(f"{Colors.DIM}{message}{Colors.ENDC}")

    return '\n'.join(str(o) for o in output) if output else ""


def load_stress_test_questions(file_path=None):
    """Load questions from the stress test markdown file."""
    if file_path is None:
        file_path = Path(__file__).parent.parent / "Stress Test Questions.md"

    if not file_path.exists():
        print(f"{Colors.RED}Stress test file not found: {file_path}{Colors.ENDC}")
        return []

    questions = []
    with open(file_path, 'r') as f:
        content = f.read()

    # Extract numbered questions with quotes
    pattern = r'\d+\.\s+"([^"]+)"'
    matches = re.findall(pattern, content)
    return matches


def load_stress_test_questions_grouped(file_path=None):
    """Load questions from markdown file, grouped by section headers."""
    if file_path is None:
        file_path = Path(__file__).parent.parent / "Stress Test Questions.md"

    if not file_path.exists():
        print(f"{Colors.RED}Stress test file not found: {file_path}{Colors.ENDC}")
        return []

    with open(file_path, 'r') as f:
        content = f.read()

    groups = []
    current_section = None
    current_questions = []

    for line in content.split('\n'):
        # Check for section headers (## Header)
        header_match = re.match(r'^## (.+)$', line)
        if header_match:
            # Save previous section
            if current_section and current_questions:
                groups.append((current_section, current_questions))
            current_section = header_match.group(1).strip()
            current_questions = []
            continue

        # Check for numbered questions with quotes
        question_match = re.match(r'\d+\.\s+"([^"]+)"', line)
        if question_match and current_section:
            current_questions.append(question_match.group(1))

    # Save last section
    if current_section and current_questions:
        groups.append((current_section, current_questions))

    return groups


# Mixed-topic conversation to test context switching
MIXED_TOPIC_QUESTIONS = [
    "What are our top 10 selling items?",           # Basic
    "How do sales compare on rainy days vs sunny days?",  # Weather
    "What are predicted sales for next week?",      # Forecasting
    "How has Salmon Roll performed over time?",     # Item-Level
    "Do we have any data for October 2025?",        # Edge Case
    "How are we doing?",                            # Vague
    "How do sales perform during Country Market?",  # Events
    "How much have we discounted in total?",        # Discount
    "How many days of data do we have?",            # Data Quality
]


def setup_logging(log_dir="logs"):
    """Create logs directory and return timestamped log file path."""
    log_path = Path(__file__).parent.parent / log_dir
    log_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"stress_test_{timestamp}.log"
    return log_file


class LogWriter:
    """Writes to both console and file."""
    def __init__(self, log_file=None, use_colors=True):
        self.log_file = log_file
        self.use_colors = use_colors
        self.file_handle = None
        if log_file:
            self.file_handle = open(log_file, 'w', encoding='utf-8')

    def write(self, text, color=None):
        """Write text to console (with optional color) and file (plain)."""
        # Console output with color
        if color and self.use_colors:
            print(f"{color}{text}{Colors.ENDC}", end='')
        else:
            print(text, end='')

        # File output without color
        if self.file_handle:
            # Strip ANSI codes for file
            plain_text = re.sub(r'\033\[[0-9;]*m', '', text)
            self.file_handle.write(plain_text)
            self.file_handle.flush()

    def writeln(self, text="", color=None):
        """Write text with newline."""
        self.write(text + "\n", color)

    def close(self):
        if self.file_handle:
            self.file_handle.close()


def interactive_mode(chat_client, agent_client, project_id, agent, verbose=False):
    """Run interactive chat session."""
    print(f"\n{Colors.GREEN}Starting interactive session with: {agent.display_name}{Colors.ENDC}")
    print(f"{Colors.DIM}Type 'quit' or 'exit' to end, 'new' for new conversation{Colors.ENDC}\n")

    conversation = create_conversation(chat_client, project_id, agent.name)
    print(f"{Colors.DIM}Conversation created: {conversation.name.split('/')[-1]}{Colors.ENDC}\n")

    while True:
        try:
            user_input = input(f"{Colors.BOLD}You:{Colors.ENDC} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

        if not user_input:
            continue

        if user_input.lower() in ('quit', 'exit', 'q'):
            print("Goodbye!")
            break

        if user_input.lower() == 'new':
            conversation = create_conversation(chat_client, project_id, agent.name)
            print(f"{Colors.GREEN}New conversation started{Colors.ENDC}\n")
            continue

        try:
            print(f"\n{Colors.BLUE}Agent:{Colors.ENDC} ", end="", flush=True)
            responses = send_message(chat_client, project_id, agent.name, conversation.name, user_input)

            for response in responses:
                formatted = format_response(response, verbose)
                if formatted:
                    print(formatted)
            print()

        except google_exceptions.GoogleAPICallError as e:
            print(f"{Colors.RED}API Error: {e}{Colors.ENDC}\n")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.ENDC}\n")


def run_stress_test(chat_client, agent_client, project_id, agent, limit=None, verbose=False):
    """Run stress test questions against the agent."""
    questions = load_stress_test_questions()

    if not questions:
        print(f"{Colors.RED}No questions found in stress test file{Colors.ENDC}")
        return

    if limit:
        questions = questions[:limit]

    print(f"\n{Colors.GREEN}Running {len(questions)} stress test questions against: {agent.display_name}{Colors.ENDC}\n")

    results = []
    conversation = create_conversation(chat_client, project_id, agent.name)

    for i, question in enumerate(questions, 1):
        print(f"{Colors.BOLD}[{i}/{len(questions)}]{Colors.ENDC} {question}")
        print("-" * 60)

        try:
            responses = send_message(chat_client, project_id, agent.name, conversation.name, question)

            response_text = ""
            for response in responses:
                formatted = format_response(response, verbose)
                if formatted:
                    response_text += formatted
                    print(formatted)

            results.append({
                "question": question,
                "status": "success",
                "response_length": len(response_text)
            })
            print()

        except google_exceptions.GoogleAPICallError as e:
            print(f"{Colors.RED}API Error: {e}{Colors.ENDC}")
            results.append({
                "question": question,
                "status": "api_error",
                "error": str(e)
            })
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.ENDC}")
            results.append({
                "question": question,
                "status": "error",
                "error": str(e)
            })

        print()

        # Create new conversation every 10 questions to avoid context overflow
        if i % 10 == 0 and i < len(questions):
            conversation = create_conversation(chat_client, project_id, agent.name)
            print(f"{Colors.DIM}--- New conversation started ---{Colors.ENDC}\n")

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"  Total: {len(results)}")
    print(f"  {Colors.GREEN}Success: {success}{Colors.ENDC}")
    print(f"  {Colors.RED}Failed: {len(results) - success}{Colors.ENDC}")

    return results


def run_stress_test_grouped(chat_client, agent_client, project_id, agent,
                            limit=None, verbose=False, log_file=None):
    """Run stress test with conversation-per-group strategy and optional file logging."""
    start_time = datetime.now()

    # Setup logging
    use_colors = sys.stdout.isatty()
    log = LogWriter(log_file=log_file, use_colors=use_colors)

    # Load grouped questions
    groups = load_stress_test_questions_grouped()
    if not groups:
        log.writeln("No question groups found in stress test file", Colors.RED)
        log.close()
        return []

    # Add mixed-topic group for context switching test
    groups.append(("Context Switching Test", MIXED_TOPIC_QUESTIONS))

    # Count total questions
    total_questions = sum(len(qs) for _, qs in groups)
    if limit:
        # Apply limit across all questions
        remaining = limit
        limited_groups = []
        for group_name, questions in groups:
            if remaining <= 0:
                break
            take = min(len(questions), remaining)
            limited_groups.append((group_name, questions[:take]))
            remaining -= take
        groups = limited_groups
        total_questions = sum(len(qs) for _, qs in groups)

    # Header
    log.writeln("=" * 80)
    log.writeln("STRESS TEST RESULTS", Colors.BOLD)
    log.writeln(f"Agent: {getattr(agent, 'display_name', agent.name.split('/')[-1])}")
    log.writeln(f"Date: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.writeln(f"Total Questions: {total_questions}")
    log.writeln(f"Conversation Groups: {len(groups)}")
    if log_file:
        log.writeln(f"Log File: {log_file}")
    log.writeln("=" * 80)
    log.writeln()

    results = []
    question_num = 0

    for group_idx, (group_name, questions) in enumerate(groups, 1):
        # Create new conversation for each group
        conversation = create_conversation(chat_client, project_id, agent.name)

        log.writeln()
        log.writeln(f"## {group_name} (Conversation {group_idx})", Colors.HEADER)
        log.writeln("-" * 80)

        for q_idx, question in enumerate(questions, 1):
            question_num += 1
            log.writeln()
            log.writeln(f"[{question_num}/{total_questions}] {question}", Colors.BOLD)
            log.writeln("-" * 60)

            try:
                responses = send_message(chat_client, project_id, agent.name,
                                        conversation.name, question)

                response_text = ""
                sql_text = ""
                has_chart = False

                for response in responses:
                    formatted = format_response(response, verbose)
                    if formatted:
                        response_text += formatted

                    # Extract SQL for logging
                    if hasattr(response, 'system_message'):
                        sys_msg = response.system_message
                        if hasattr(sys_msg, 'data') and sys_msg.data:
                            if hasattr(sys_msg.data, 'generated_sql') and sys_msg.data.generated_sql:
                                sql_text = sys_msg.data.generated_sql
                        if hasattr(sys_msg, 'chart') and sys_msg.chart:
                            chart_str = str(sys_msg.chart)
                            if chart_str and len(chart_str) > 10:
                                has_chart = True

                # Write response
                if sql_text:
                    log.writeln(f"SQL: {sql_text[:200]}{'...' if len(sql_text) > 200 else ''}", Colors.CYAN)
                if response_text:
                    # Truncate very long responses for readability
                    display_text = response_text[:500] + "..." if len(response_text) > 500 else response_text
                    log.writeln(display_text, Colors.GREEN)
                if has_chart:
                    log.writeln("[Chart generated]", Colors.YELLOW)

                log.writeln("Status: SUCCESS", Colors.GREEN)

                results.append({
                    "group": group_name,
                    "question": question,
                    "status": "success",
                    "response_length": len(response_text),
                    "has_sql": bool(sql_text),
                    "has_chart": has_chart
                })

            except google_exceptions.GoogleAPICallError as e:
                log.writeln(f"API Error: {e}", Colors.RED)
                log.writeln("Status: FAILED", Colors.RED)
                results.append({
                    "group": group_name,
                    "question": question,
                    "status": "api_error",
                    "error": str(e)
                })
            except Exception as e:
                log.writeln(f"Error: {e}", Colors.RED)
                log.writeln("Status: FAILED", Colors.RED)
                results.append({
                    "group": group_name,
                    "question": question,
                    "status": "error",
                    "error": str(e)
                })

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    success = sum(1 for r in results if r["status"] == "success")
    failed = [r for r in results if r["status"] != "success"]

    log.writeln()
    log.writeln("=" * 80)
    log.writeln("SUMMARY", Colors.BOLD)
    log.writeln("=" * 80)
    log.writeln(f"Total: {len(results)}")
    log.writeln(f"Success: {success}", Colors.GREEN)
    log.writeln(f"Failed: {len(failed)}", Colors.RED if failed else None)
    log.writeln(f"Duration: {duration}")

    if failed:
        log.writeln()
        log.writeln("Failed questions:", Colors.RED)
        for r in failed:
            log.writeln(f"  - [{r['group']}] {r['question']}")
            if 'error' in r:
                log.writeln(f"    Error: {r['error'][:100]}")

    # Questions with SQL that used daily_summary (for verification)
    daily_summary_questions = [r for r in results if r.get('has_sql') and 'daily_summary' in str(r)]
    if daily_summary_questions:
        log.writeln()
        log.writeln("Note: Check SQL in Weather Correlations group for ai.daily_summary usage")

    log.writeln()
    log.writeln("=" * 80)

    log.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test the Conversational Analytics agent from CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Interactive mode
  %(prog)s "What are top sellers?"      # Single query
  %(prog)s --stress-test                # Run all stress test questions
  %(prog)s --stress-test --limit 5      # Run first 5 questions only
  %(prog)s --list-agents                # List available agents
        """
    )

    parser.add_argument("query", nargs="?", help="Single query to send to the agent")
    parser.add_argument("--project", "-p", default=DEFAULT_PROJECT_ID,
                        help=f"GCP project ID (default: {DEFAULT_PROJECT_ID})")
    parser.add_argument("--agent", "-a", help="Agent display name to use (default: first available)")
    parser.add_argument("--list-agents", "-l", action="store_true", help="List available agents and exit")
    parser.add_argument("--stress-test", "-s", action="store_true", help="Run stress test questions")
    parser.add_argument("--limit", "-n", type=int, help="Limit number of stress test questions")
    parser.add_argument("--grouped", "-g", action="store_true",
                        help="Group questions by category (one conversation per group)")
    parser.add_argument("--log", "-o", action="store_true",
                        help="Log output to timestamped file in logs/")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output including raw messages")

    args = parser.parse_args()

    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')

    # Initialize clients
    try:
        agent_client = geminidataanalytics.DataAgentServiceClient()
        chat_client = geminidataanalytics.DataChatServiceClient()
    except Exception as e:
        print(f"{Colors.RED}Failed to initialize clients: {e}{Colors.ENDC}")
        print(f"{Colors.DIM}Make sure you've run: gcloud auth application-default login{Colors.ENDC}")
        sys.exit(1)

    # List agents
    try:
        agents = get_agents(agent_client, args.project)
    except google_exceptions.GoogleAPICallError as e:
        print(f"{Colors.RED}Failed to list agents: {e}{Colors.ENDC}")
        sys.exit(1)

    if not agents:
        print(f"{Colors.RED}No agents found in project {args.project}{Colors.ENDC}")
        sys.exit(1)

    # Just list agents
    if args.list_agents:
        print(f"\n{Colors.BOLD}Available agents in {args.project}:{Colors.ENDC}\n")
        for agent in agents:
            name = getattr(agent, 'display_name', None) or agent.name.split('/')[-1]
            print(f"  - {name}")
            if hasattr(agent, 'data_analytics_agent'):
                ctx = agent.data_analytics_agent.published_context
                if hasattr(ctx, 'datasource_references'):
                    try:
                        refs = ctx.datasource_references
                        # Proto objects need different access
                        ref_names = [str(k) for k in refs._pb.keys()] if hasattr(refs, '_pb') else list(refs)
                        if ref_names:
                            print(f"    {Colors.DIM}Datasources: {', '.join(ref_names)}{Colors.ENDC}")
                    except Exception:
                        pass  # Skip if we can't extract datasource info
        print()
        return

    # Select agent
    if args.agent:
        agent = next((a for a in agents if getattr(a, 'display_name', '') == args.agent), None)
        if not agent:
            print(f"{Colors.RED}Agent '{args.agent}' not found{Colors.ENDC}")
            print(f"Available: {', '.join(getattr(a, 'display_name', a.name.split('/')[-1]) for a in agents)}")
            sys.exit(1)
    else:
        agent = agents[-1]  # Most recently created

    print(f"{Colors.DIM}Using agent: {getattr(agent, 'display_name', agent.name.split('/')[-1])}{Colors.ENDC}")

    # Execute based on mode
    if args.stress_test:
        if args.grouped:
            # Grouped mode with optional logging
            log_file = setup_logging() if args.log else None
            if log_file:
                print(f"{Colors.DIM}Logging to: {log_file}{Colors.ENDC}")
            run_stress_test_grouped(chat_client, agent_client, args.project, agent,
                                   args.limit, args.verbose, log_file)
        else:
            # Original mode (batch of 10)
            run_stress_test(chat_client, agent_client, args.project, agent, args.limit, args.verbose)
    elif args.query:
        # Single query mode
        conversation = create_conversation(chat_client, args.project, agent.name)
        try:
            responses = send_message(chat_client, args.project, agent.name, conversation.name, args.query)
            for response in responses:
                formatted = format_response(response, args.verbose)
                if formatted:
                    print(formatted)
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.ENDC}")
            sys.exit(1)
    else:
        # Interactive mode
        interactive_mode(chat_client, agent_client, args.project, agent, args.verbose)


if __name__ == "__main__":
    main()
