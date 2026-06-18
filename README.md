# NextGen Delivery 🚚

**Agentic last-mile logistics for the Caribbean.**
*Delivering the future, today.*

A consumer delivery app — food, grocery, pharmacy and parcel — powered by a multi-agent AI **dispatch-and-routing engine**, built for a region where addresses are landmarks and last-mile is broken. Built for Barbados, designed for CARIFORUM-wide replication, and portable to every emerging market with informal addressing.

> Submission for the **Future Caribbean Global Agentic AI Buildathon (2026)** — Track 01: AI for Tourism & Transportation.

**🔗 Live demo:** open `app-preview.html` · **Founder site:** open `index.html`

---

## The problem

Delivery across the Caribbean breaks in ways global apps never designed for:

- **No formal addresses** — people navigate by landmarks ("third house past the blue rum shop"). Pin-drop apps fail.
- **Fragmented last-mile** — dozens of tiny, uncoordinated couriers per island.
- **Manual cross-island movement** — parcels hand-carried across ferries and air cargo.
- **MSMEs locked out** — small merchants can't afford professional logistics.

## The solution

An **agentic dispatch-and-routing engine** — the exportable core asset — front-ended by a simple consumer app. Order by text, voice or WhatsApp; describe your location by landmark; let the agents do the rest.

## Agentic architecture

| Agent | Role | Human-in-the-loop |
|---|---|---|
| Intake Agent | Parse order from text/voice/WhatsApp | Customer confirms order |
| **Address Resolution Agent** ⭐ | Landmark → precise, reusable drop point | Confirm first-time locations |
| Merchant Agent | Stock check + ordering | Approve substitutions |
| Dispatch & Routing Agent | Assign, batch, optimize routes | Driver accepts |
| Exception & Recovery Agent | Detect failures + re-plan | Escalate edge cases to ops |
| Comms Agent | Proactive customer updates | — |
| Logistics Orchestration Agent | Cross-island ferry/air-cargo hand-offs (Phase 2+) | Ops confirms hand-offs |

📊 **Full agentic workflow diagram:** see `agentic-workflow.pdf` in this repository.

## The moat

Landmark address resolution is a **proprietary, compounding data advantage** — every delivery teaches the engine the region's informal geography. Drawn directly from the founder's 13 years of real-time hospital dispatch.

## Roadmap

1. **Phase 1 — Barbados:** prove the engine on multi-category last-mile; 100% electric fleet.
2. **Phase 2 — CARIFORUM:** replicate into a second member state; cross-island orchestration.
3. **Phase 3 — Software-services export:** license the engine to regional operators.

## Tech (planned)

Open-source LLMs (Llama/Qwen-class) on NVIDIA H200 compute · open-source multi-agent orchestration + OpenClaw · OpenStreetMap + geospatial reasoning · vector DB for location memory · WhatsApp Business API + voice transcription.

## Traction

Architected for CARIFORUM-wide replication · aligned with the EU–CARIFORUM EPA and CSME · climate-aligned electric fleet.

## Founder

**Martino Bayley** — Bridgetown, Barbados. 13+ years as an Emergency Medical Dispatcher; turning real-time dispatch expertise into an agentic system.
📫 martino.bayley@gmail.com

---

*If it works in the Caribbean, it scales globally.*
