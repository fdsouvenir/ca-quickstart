# Stress Test Questions

Sample queries to test the Conversational Analytics agent against the restaurant data.

---

## Basic Queries

1. "What are our top 10 selling items?"
2. "How much did we make last Saturday?"
3. "What's our total sales for June 2025?"
4. "How many items did we sell yesterday?"
5. "What was our lowest sales day?"

## Category Analysis

6. "Which category generates the most revenue?"
7. "Compare food vs drink sales"
8. "Show me a bar chart of sales by primary category"
9. "What's our average ticket by category?"
10. "Which category has the most items?"

## Time Patterns

11. "What day of the week has the highest sales?"
12. "Chart our daily sales trend for the last 3 months"
13. "How do weekends compare to weekdays?"
14. "What's our best performing month?"
15. "Show me sales by hour of the day" *(edge case - data is daily)*
16. "What time do we sell the most sushi?" *(edge case - no hourly data)*

## Weather Correlations

17. "How do sales compare on rainy days vs sunny days?"
18. "What items sell best when it's cold outside?"
19. "Is there a correlation between temperature and sales? Show me a scatter plot"
20. "What's our average sales when it snows?"
21. "Do hot days affect drink sales?"
22. "What's our best selling item on days above 80 degrees?"

## Event Impact

23. "How do sales perform during Country Market?"
24. "What's our best selling item during local events?"
25. "Compare event days to non-event days"
26. "Which event drives the most sales?"
27. "What events happen in July?"
28. "Show me sales lift during Fall Fest"

## Forecasting

29. "What are predicted sales for next week?"
30. "Show me the sales forecast as a line chart"
31. "What's the predicted sales for next Saturday?"
32. "How accurate have our forecasts been?"
33. "What's the forecast confidence interval?"

## Anomaly Detection

34. "Were there any unusual sales days?"
35. "What days had unexpectedly high sales?"
36. "Show me any sales anomalies in the last month"
37. "Did any items have unusual spikes?"

## Item-Level Analysis

38. "How has Salmon Roll performed over time?"
39. "What's our most consistent seller?"
40. "Which items have declining sales?"
41. "What items are only sold on certain days?"
42. "Compare Dragon Roll vs Rainbow Roll"
43. "What's our highest margin item?" *(edge case - no cost data)*

## Comparison Queries

44. "Compare June to July sales"
45. "How does this month compare to last month?"
46. "Year-over-year growth for appetizers" *(edge case - limited date range)*
47. "Week over week sales trend"
48. "Compare Saturday vs Sunday performance"

## Discount Analysis

49. "How much have we discounted in total?"
50. "What items get discounted the most?"
51. "What's our discount rate by category?"
52. "Which day has the highest discounts?"
53. "Show me discount trends over time"

## Complex/Multi-Dimensional

54. "What sells best on rainy weekends?"
55. "Top 5 items during summer events"
56. "Compare weekend sales in summer vs winter"
57. "What's our average daily sales by month? Show as a bar chart"
58. "Best category on cold weekdays with no events"
59. "How do holidays affect different categories?"

## Visualization Requests

60. "Create a heatmap of sales by day and category"
61. "Show me a pie chart of category distribution"
62. "Line chart of weekly sales with forecast overlay"
63. "Bar chart comparing top 10 items"
64. "Scatter plot of temperature vs beverage sales"

## Edge Cases

65. "Do we have any data for October 2025?" *(outside range)*
66. "What were sales on Christmas?"
67. "Show me items with the highest discounts"
68. "What items have we stopped selling?"
69. "Sales for the Chicago location" *(only one location)*
70. "What's our profit margin?" *(no cost data)*

## Vague/Ambiguous (Tests Interpretation)

71. "How are we doing?"
72. "What should I order more of?"
73. "Any interesting patterns?"
74. "What's trending?"
75. "Give me insights"
76. "What should I know about last week?"

## Data Quality

77. "How many days of data do we have?"
78. "Are there any gaps in our data?"
79. "When does our data start and end?"
80. "How many unique items are in the database?"
81. "What's our data freshness?"

## Natural Language Variations

82. "top sellers" *(minimal query)*
83. "sales" *(extremely vague)*
84. "Show me everything" *(too broad)*
85. "What about the sushi?" *(context-dependent)*
86. "Can you make a chart?" *(no specific data)*

---

## Expected Behaviors

| Query Type | Expected Response |
|------------|-------------------|
| Basic queries | Direct answer with optional chart |
| Weather/Event correlation | Comparison with supporting data |
| Forecasting | Chart with confidence bounds |
| Edge cases | Graceful explanation of data limits |
| Vague queries | Clarifying question or best-guess interpretation |
| Visualization requests | Appropriate chart type |

## Notes

- **Data range**: December 2024 - September 2025 (~200 days)
- **Weather coverage**: Through August 2025 only
- **Granularity**: Daily (no hourly data)
- **Location**: Single location (Frankfort, IL)
