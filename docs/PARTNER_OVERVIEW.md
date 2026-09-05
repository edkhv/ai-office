# AI Office — proposed Local AI Station evaluation

AI Office is an early project from Saint Petersburg for Russian-speaking small and medium-sized businesses. It explores a compact local-first business assistant: an operational workforce, an executive assistant and explainable management figures. The public repository contains a working software prototype with synthetic examples, not customer deployment evidence.

The proposed hardware configuration is a Local AI Station with 96–128 GB of memory. The manufacturer and compute architecture are selected for the workload. A station may host both the application and inference; a separate management computer is optional. A separate 4G/5G router and UPS are future deployment components; neither is required by the current demo. Development does not depend on purchasing the target station.

Software already present: FastAPI/Pydantic application, separate durable worker, CrewAI planner/reviewer adapter, Ollama and compatible HTTP paths, Qdrant document retrieval with access checks and citations, approved local tasks, deterministic financial calculations and lineage, audit and an English/Russian dashboard. The default demo uses clearly labeled deterministic responses and synthetic data. Validation details and known dependency findings are in VALIDATION.md and DEPENDENCY_REVIEW.md.

**Target hardware; not yet validated on device.** We need to establish exact SKU/revision, memory topology, OS and boot/storage, transport and host requirements, vendor driver/firmware versions, supported runtimes and models, licensing, cooling, power requirements and recovery behavior. The generic HTTP adapter does not imply device compatibility.

We would welcome a discussion about an evaluation unit or possible developer pricing, current runtime documentation, a supported model list and a technical contact. In return, the project could provide reproducible software and on-device test reports, engineering feedback, Russian-language material localization and a demonstration case agreed by both sides.

Future cooperation could include integration services or regional representation after technical and commercial discussion. No current official partnership, certified integration, confirmed discount, procurement volume or revenue is claimed. Any procurement would use mutually agreed official channels and applicable rules. This document is a discussion brief; no message has been sent to the manufacturer by the coding workflow.

Suggested review order: README → live demo / screenshots → ARCHITECTURE → LOCAL_AI_STATION_VALIDATION → VALIDATION and ROADMAP.
