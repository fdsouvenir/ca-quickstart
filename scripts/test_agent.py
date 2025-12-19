#!/usr/bin/env python3
"""
CLI tool to test the Conversational Analytics agent without the Streamlit UI.

Usage:
    # Interactive mode
    python scripts/test_agent.py

    # Single query
    python scripts/test_agent.py "What are our top 10 selling items?"

    # Run stress test questions
    python scripts/test_agent.py --stress-test

    # List available agents
    python scripts/test_agent.py --list-agents
"""

import argparse
import json
import re
import sys
import os
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
