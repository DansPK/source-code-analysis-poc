ai-source-scanner/
├── app/
│   ├── main.py
│   │
│   ├── source/
│   │   ├── loader.py
│   │   ├── git_loader.py
│   │   └── local_loader.py
│   │
│   ├── repository/
│   │   ├── analyzer.py
│   │   ├── language_detector.py
│   │   ├── file_filter.py
│   │   └── code_map.py
│   │
│   ├── scanners/
│   │   ├── semgrep_scanner.py
│   │   └── base_scanner.py
│   │
│   ├── findings/
│   │   ├── parser.py
│   │   ├── model.py
│   │   └── deduplicator.py
│   │
│   ├── context/
│   │   ├── builder.py
│   │   ├── cross_file.py
│   │   ├── symbol_resolver.py
│   │   └── call_graph.py
│   │
│   ├── ai/
│   │   ├── analyzer.py
│   │   ├── validator.py
│   │   ├── prompts.py
│   │   └── client.py
│   │
│   ├── agent/
│   │   ├── security_agent.py
│   │   ├── explainer.py
│   │   └── remediation.py
│   │
│   ├── report/
│   │   ├── reporter.py
│   │   ├── json_report.py
│   │   └── cli_report.py
│   │
│   ├── models/
│   │   ├── finding.py
│   │   ├── repository.py
│   │   └── analysis.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   └── utils/
│       ├── filesystem.py
│       └── logging.py
│
├── tests/
│   ├── vulnerable_samples/
│   ├── test_scanner.py
│   ├── test_context.py
│   └── test_ai_analysis.py
│
├── rules/
│   └── semgrep/
│
├── reports/
│
├── temp/
│
├── .env
├── .gitignore
├── requirements.txt
├── README.md
└── pyproject.toml