import pandas as pd
import json
import copy

import proto
from google.protobuf.json_format import MessageToDict

import streamlit as st

# Based off documentation: https://cloud.google.com/gemini/docs/conversational-analytics-api/build-agent-sdk#define_helper_functions

# ============================================================================
# Column Formatting
# ============================================================================

def detect_column_format(col_name):
    """Detect format based on column name patterns."""
    col = col_name.lower()

    # Dollar patterns: ends with sales/revenue/discount/cost/price, or contains 'bound'
    if any(col.endswith(s) for s in ('_sales', 'sales', '_revenue', '_discount', '_cost', '_price')):
        return "$ %.2f"
    if 'bound' in col or col == 'predicted_sales':  # forecast bounds
        return "$ %.2f"

    # Temperature patterns: contains 'temp'
    if 'temp' in col:
        return "%.1f°F"

    # Precipitation patterns: ends with '_in' (inches)
    if col.endswith('_in'):
        return '%.2f"'

    # Quantity patterns: contains quantity/count/sold/items
    if any(x in col for x in ('quantity', 'count', 'sold', 'items')):
        return "%d"

    return None  # No special formatting


def build_column_config(df):
    """Build Streamlit column_config from DataFrame columns."""
    config = {}
    for col in df.columns:
        fmt = detect_column_format(col)
        if fmt:
            config[col] = st.column_config.NumberColumn(col, format=fmt)
    return config


# ============================================================================
# Chart Theming
# ============================================================================

CHART_THEME = {
    "config": {
        "padding": {"left": 20, "right": 20, "top": 20, "bottom": 20},
        "title": {"fontSize": 16, "anchor": "start"},
        "axis": {
            "labelFontSize": 11,
            "titleFontSize": 12,
            "gridColor": "#e8eaed",
            "domainColor": "#dadce0"
        },
        "view": {"stroke": "transparent"},
        "bar": {"color": "#4285F4"},
        "line": {"color": "#4285F4", "strokeWidth": 2},
        "point": {"color": "#4285F4", "size": 60}
    }
}


def apply_chart_theme(vega_spec):
    """Merge theme config into Vega-Lite spec, preserving agent's config."""
    themed = copy.deepcopy(vega_spec)
    existing = themed.get("config", {})

    for key, value in CHART_THEME["config"].items():
        if key not in existing:
            existing[key] = value
        elif isinstance(value, dict) and isinstance(existing.get(key), dict):
            # Merge nested dicts (theme is default, agent values override)
            existing[key] = {**value, **existing[key]}

    themed["config"] = existing

    # Ensure chart has reasonable dimensions
    if "width" not in themed:
        themed["width"] = "container"
    if "height" not in themed:
        themed["height"] = 400

    return themed

def handle_text_response(resp):
  parts = getattr(resp, 'parts')
  text = ''.join(parts)
  # Escape $ signs to render as literal dollar signs, not LaTeX
  text = text.replace('$', '\\$')
  st.markdown(text)

def display_schema(data):
  fields = getattr(data, 'fields')
  df = pd.DataFrame({
    "Column": map(lambda field: getattr(field, 'name'), fields),
    "Type": map(lambda field: getattr(field, 'type'), fields),
    "Description": map(lambda field: getattr(field, 'description', '-'), fields),
    "Mode": map(lambda field: getattr(field, 'mode'), fields)
  })
  with st.expander("**Schema**:"):
    st.dataframe(df)

def format_looker_table_ref(table_ref):
 return 'lookmlModel: {}, explore: {}, lookerInstanceUri: {}'.format(table_ref.lookml_model, table_ref.explore, table_ref.looker_instance_uri)

def format_bq_table_ref(table_ref):
  return '{}.{}.{}'.format(table_ref.project_id, table_ref.dataset_id, table_ref.table_id)

def display_datasource(datasource):
  source_name = ''
  if 'studio_datasource_id' in datasource:
   source_name = getattr(datasource, 'studio_datasource_id')
  elif 'looker_explore_reference' in datasource:
   source_name = format_looker_table_ref(getattr(datasource, 'looker_explore_reference'))
  else:
    source_name = format_bq_table_ref(getattr(datasource, 'bigquery_table_reference'))

  st.markdown("**Data source**: " + source_name)
  display_schema(datasource.schema)

def handle_schema_response(resp):
  if 'query' in resp:
    st.markdown("**Query:** " + resp.query.question)
  elif 'result' in resp:
    st.markdown("**Schema resolved.**")
    for datasource in resp.result.datasources:
      display_datasource(datasource)

def handle_data_response(resp):
  if 'query' in resp:
    query = resp.query
    st.markdown("**Retrieval query**")
    st.markdown('**Query name:** {}'.format(query.name))
    st.markdown('**Question:** {}'.format(query.question))
    for datasource in query.datasources:
      display_datasource(datasource)
  elif 'generated_sql' in resp:
    with st.expander("**SQL generated:**"):
        st.code(resp.generated_sql, language="sql")
  elif 'result' in resp:
    st.markdown('**Data retrieved:**')

    fields = [field.name for field in resp.result.schema.fields]
    d = {}
    for el in resp.result.data:
      for field in fields:
        if field in d:
          d[field].append(el[field])
        else:
          d[field] = [el[field]]

    df = pd.DataFrame(d)

    st.dataframe(df, column_config=build_column_config(df), use_container_width=True)
    st.session_state.lastDataFrame = df

def handle_chart_response(resp):
  def _convert(v):
    if isinstance(v, proto.marshal.collections.maps.MapComposite):
      return {k: _convert(v) for k, v in v.items()}
    elif isinstance(v, proto.marshal.collections.RepeatedComposite):
      return [_convert(el) for el in v]
    elif isinstance(v, (int, float, str, bool)):
      return v
    else:
      return MessageToDict(v)

  if 'query' in resp:
    st.markdown(resp.query.instructions)
  elif 'result' in resp:
    vega_spec = _convert(resp.result.vega_config)
    themed_spec = apply_chart_theme(vega_spec)
    st.vega_lite_chart(themed_spec, use_container_width=True)

def show_message(msg):
  m = msg.system_message
  if 'text' in m:
    handle_text_response(getattr(m, 'text'))
  elif 'schema' in m:
    handle_schema_response(getattr(m, 'schema'))
  elif 'data' in m:
    handle_data_response(getattr(m, 'data'))
  elif 'chart' in m:
    handle_chart_response(getattr(m, 'chart'))
