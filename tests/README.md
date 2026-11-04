# Automated Evaluation & Testing Suite

A comprehensive automated testing and evaluation framework built on **pytest**, declarative YAML scenarios, and **Langfuse** scoring for end-to-end multi-agent verification.

## 1. Directory Structure

```
tests/
├── eval/
│   ├── scenarios.yaml     # Declarative multi-turn evaluation scenarios
│   ├── test_eval_suite.py # Main pytest test suite runner
│   └── utils.py           # Evaluation assertion engine and Langfuse integration
├── fixtures/              # Sample datasets (CSV, XLSX, corrupted inputs)
└── conftest.py            # Global pytest fixtures and environment hooks
```

## 2. Evaluation Scenarios

The test suite contains 6 multi-turn benchmark scenarios validating the entire system lifecycle:

| Scenario | Name | Test Scope |
| :---: | :--- | :--- |
| **1** | `onboarding` | Conversational greetings, system capability explanations, and direct algorithmic reasoning without unnecessary SQL calls |
| **2** | `sql_analytics` | Analytical SQL queries: aggregations, GROUP BY, date-range filters, ORDER BY, and LIMIT clauses |
| **3** | `ml_analysis` | Statistical modeling, K-Means clustering, correlation matrices, and Plotly visualization generation |
| **4** | `db_mutations` | Safe table modifications (`INSERT`, `UPDATE`, `DELETE`) with required `RETURNING *` clauses and rollback verification |
| **5** | `robustness` | Edge cases: queries targeting non-existent tables/columns, case insensitivity, graceful error explanations |
| **6** | `data_ingestion` | User file uploads (CSV/XLSX), automatic table creation, and subsequent schema querying |

## 3. Running the Tests

#### Step 1. Run Complete Evaluation Suite
```bash
uv run pytest tests/eval/test_eval_suite.py -v
```

#### Step 2. Run Individual Scenario
```bash
uv run pytest tests/eval/test_eval_suite.py -k "sql_analytics" -v -s
```

## 4. Langfuse Scoring & Metrics

Each scenario execution is automatically recorded as a standalone trace in Langfuse with automated score evaluation for:

* Correct intent routing (`route_score`);
* SQL syntax validity and execution success (`sql_validity_score`);
* Expected numerical metrics and key findings presence;
* Plotly figure structure and palette compliance.

## 5. Test Fixtures & Data

Pre-packaged test assets in `tests/fixtures/`:

* `inventory_items.csv`: Standard CSV catalog for ingestion testing.
* `simple_catalog.xlsx` & `multi_sheet_data.xlsx`: Excel workbooks testing multi-sheet ingestion.
* `empty.csv` & `corrupted.xlsx`: Malformed data testing system robustness and graceful degradation.
