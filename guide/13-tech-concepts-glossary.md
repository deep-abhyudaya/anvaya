# 13 — Tech Concepts Glossary (Simple English)

This is a no-jargon dictionary for the technologies and ideas used in ANVAYA.

| Term | Simple meaning |
|---|---|
| **Next.js** | A React framework that adds routing, server rendering, and fast builds. |
| **App Router** | Next.js's new way to create pages by putting `page.tsx` files inside folders. |
| **Dynamic route** | A URL with a variable part, like `/incidents/123`. The `123` is dynamic. |
| **React Query** | A library that fetches server data, caches it, and refreshes it automatically. |
| **TypeScript** | JavaScript with types, so the compiler can catch mistakes earlier. |
| **Tailwind CSS** | A way to write CSS styles using small utility class names in the HTML. |
| **shadcn/ui** | A set of pre-built React components styled with Tailwind. |
| **FastAPI** | A fast Python framework for building REST APIs. |
| **Pydantic** | A Python library that validates data using typed classes. |
| **SQLModel** | A library that lets one Python class describe a database table and a JSON schema. |
| **SQLAlchemy** | A Python toolkit for working with databases through Python code. |
| **PostgreSQL** | A popular, production-grade open-source relational database. |
| **SQLite** | A small file-based database, good for local development. |
| **ORM** | Object-Relational Mapper: lets you work with database rows as Python objects. |
| **Migration** | A script that changes the database structure safely over time. |
| **Alembic** | The migration tool that works with SQLAlchemy. |
| **Uvicorn** | A fast Python web server that runs FastAPI. |
| **CORS** | Cross-Origin Resource Sharing: the rule that lets a frontend on one server talk to a backend on another. |
| **REST API** | A way for two programs to talk over HTTP using URLs and JSON. |
| **Endpoint** | One URL on an API, e.g. `GET /api/v1/incidents`. |
| **JSON** | JavaScript Object Notation: a text format for sending structured data. |
| **Dependency injection** | A design where the framework gives a function the things it needs (like a database session). |
| **OpenAPI / Swagger** | Auto-generated interactive documentation for an API. |
| **Isolation Forest** | A machine learning algorithm that finds outliers by randomly isolating data points. |
| **Logistic Regression** | A simple ML algorithm that predicts the probability of something being true or false. |
| **StandardScaler** | A pre-processing step that puts all numbers on the same scale. |
| **Feature** | One measurable property of an event, e.g. `hour_of_day`. |
| **Feature extraction** | Turning raw events into numbers that a model can use. |
| **Training** | Showing a model many examples so it learns patterns. |
| **Inference** | Using a trained model to make a prediction on new data. |
| **Precision** | Of the things the model called attacks, how many were really attacks. |
| **Recall** | Of all real attacks, how many did the model find. |
| **F1 score** | A single number that balances precision and recall. |
| **False positive** | A normal event wrongly called an attack. |
| **False negative** | A real attack the model missed. |
| **Ground truth** | The real answer, known from labels. |
| **Counterfactual** | A "what if" question: what would happen if one thing were different. |
| **NetworkX** | A Python library for creating and analysing graphs (nodes and edges). |
| **Graph node** | A point in a graph, e.g. a computer or user. |
| **Graph edge** | A connection between two nodes, e.g. a network link. |
| **Blast radius** | How far an attack could spread from the first compromised machine. |
| **Hash** | A fixed-length fingerprint of data. Changing the data changes the hash. |
| **SHA-256** | A specific, strong hashing algorithm. |
| **Hash chain** | A sequence of records where each record's hash depends on the previous one. If anything is changed, the chain breaks. |
| **Tamper-evident** | A system that makes it obvious if someone changed data. |
| **LLM** | Large Language Model, like GPT-4o mini, used here for naming rules. |
| **Function calling** | A way to ask an LLM to return structured JSON output. |
| **Deterministic** | Producing the same output every time the same inputs are given. |
| **Seed** | A starting number for a random generator. The same seed gives the same random sequence. |
| **Data leakage** | When the model accidentally sees test data during training. It makes results look better than they are. |
| **Train / validation / test split** | Dividing data into three parts: one to train, one to tune, one to fairly evaluate. |
| **SOC** | Security Operations Centre: the team that watches for cyber attacks. |
| **Telemetry** | Stream of recorded events from computers, users, and processes. |
| **Incident lifecycle** | The stages an incident goes through from detection to closure. |
| **Self-correction** | The system improving its own rules after a miss. |
| **Audit trail** | A log of every important action, used for compliance and proof. |
| **pytest** | A tool that runs automated tests in Python. |
| **Docker** | A way to package an app with its dependencies so it runs the same everywhere. |
| **Vercel** | A cloud platform for hosting Next.js apps. |
| **Railway / Fly.io** | Cloud platforms for running backend services and databases. |
