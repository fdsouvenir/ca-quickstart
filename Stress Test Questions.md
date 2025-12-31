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
23. "Create a scatter plot showing precipitation vs daily sales"

## Event Impact

24. "How do sales perform during Country Market?"
25. "What's our best selling item during local events?"
26. "Compare event days to non-event days"
27. "Which event drives the most sales?"
28. "What events happen in July?"
29. "Show me sales lift during Fall Fest"

## Sales Forecasting

30. "What are predicted sales for next week?"
31. "Show me the sales forecast as a line chart"
32. "What's the predicted sales for next Saturday?"
33. "How accurate have our forecasts been?"
34. "What's the forecast confidence interval?"

## Weather Forecast

35. "Will it snow today?"
36. "What's the weather forecast for tomorrow?"
37. "Show me the 7-day weather forecast"
38. "Is it going to rain this weekend?"
39. "What's the high temperature on Saturday?"
40. "When is the next rainy day expected?"

## Category Forecasting

41. "How many beers should we sell tomorrow?"
42. "Forecast sushi sales for next week"
43. "Predict beer vs liquor sales for Saturday"
44. "What categories will perform best this weekend?"
45. "Show me the food forecast with confidence intervals"
46. "Compare category forecasts for the next 7 days"

## Anomaly Detection

47. "Were there any unusual sales days?"
48. "What days had unexpectedly high sales?"
49. "Show me any sales anomalies in the last month"
50. "Did any items have unusual spikes?"
51. "Any unusual beer sales recently?"
52. "Which categories spiked last week?"
53. "Were there any quantity anomalies by category?"
54. "Show me category-level anomalies as a table"

## Item-Level Analysis

55. "How has Salmon Roll performed over time?"
56. "What's our most consistent seller?"
57. "Which items have declining sales?"
58. "What items are only sold on certain days?"
59. "Compare Dragon Roll vs Rainbow Roll"
60. "What's our highest margin item?" *(edge case - no cost data)*

## Comparison Queries

61. "Compare June to July sales"
62. "How does this month compare to last month?"
63. "Year-over-year growth for appetizers" *(edge case - may have limited history)*
64. "Week over week sales trend"
65. "Compare Saturday vs Sunday performance"

## Discount Analysis

66. "How much have we discounted in total?"
67. "What items get discounted the most?"
68. "What's our discount rate by category?"
69. "Which day has the highest discounts?"
70. "Show me discount trends over time"

## Complex/Multi-Dimensional

71. "What sells best on rainy weekends?"
72. "Top 5 items during summer events"
73. "Compare weekend sales in summer vs winter"
74. "What's our average daily sales by month? Show as a bar chart"
75. "Best category on cold weekdays with no events"
76. "How do holidays affect different categories?"

## Visualization Requests

77. "Create a heatmap of sales by day and category"
78. "Show me a pie chart of category distribution"
79. "Line chart of weekly sales with forecast overlay"
80. "Bar chart comparing top 10 items"
81. "Scatter plot of temperature vs beverage sales"

## Edge Cases

82. "What were sales on Christmas?"
83. "Show me items with the highest discounts"
84. "What items have we stopped selling?"
85. "Sales for the Chicago location" *(only one location)*
86. "What's our profit margin?" *(no cost data)*
87. "What time do we sell the most?" *(no hourly data)*

## Vague/Ambiguous (Tests Interpretation)

88. "How are we doing?"
89. "What should I order more of?"
90. "Any interesting patterns?"
91. "What's trending?"
92. "Give me insights"
93. "What should I know about last week?"

## Data Quality

94. "How many days of data do we have?"
95. "Are there any gaps in our data?"
96. "When does our data start and end?"
97. "How many unique items are in the database?"
98. "What's our data freshness?"

## Natural Language Variations

99. "top sellers" *(minimal query)*
100. "sales" *(extremely vague)*
101. "Show me everything" *(too broad)*
102. "What about the sushi?" *(context-dependent)*
103. "Can you make a chart?" *(no specific data)*

---

## Context Switching Test (Conversation 19)

*Run these 9 questions consecutively in one conversation to test topic transitions:*

104. "What's the weather forecast for tomorrow?"
105. "Show me top 5 beer items"
106. "How did we do on Christmas?"
107. "Forecast sushi sales for Saturday"
108. "Any anomalies in the wine category?"
109. "Compare weekday vs weekend sales"
110. "Will it snow this week?"
111. "What's our most discounted item?"
112. "Create a pie chart of today's category mix"

## Context Switching Test (Conversation 20)

*Final comprehensive context switching test - revisits questions from different categories:*

113. "What are our top 10 selling items?"
114. "How do sales compare on rainy days vs sunny days?"
115. "What are predicted sales for next week?"
116. "How has Salmon Roll performed over time?"
117. "Do we have any data for October 2025?"
118. "How are we doing?"
119. "How do sales perform during Country Market?"
120. "How much have we discounted in total?"
121. "How many days of data do we have?"

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

- **Data range**: Query `ai.data_quality` for current coverage (earliest_date, latest_date, days_with_data)
- **Weather**: Historical actuals in `insights.local_weather`, 14-day forecast in `ai.weather_forecast` (refreshed daily)
- **Granularity**: Daily (no hourly data)
- **Location**: Single location (Frankfort, IL)
- **Total questions**: 121 (103 category questions + 18 context switching questions across 2 groups)
- **Conversation groups**: 20 (18 categories + 2 context switching tests)
