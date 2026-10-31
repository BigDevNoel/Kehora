# AI Hardware Studio — Product Requirements Document

Oct 29, 2026 · @Emma

## 1. Overview

Kehora lets anyone describe a physical thing in plain language and get it designed, verified and made: 3D-printed objects, electronics with firmware, the enclosure that fits them, laser-cut parts, and the app that controls the device. It is to hardware what AI app builders are to software.

**Problem.** Making a physical product today needs CAD skills, electronics knowledge, firmware coding, and access to printers and parts suppliers. Each is a separate expert or tool, so most people with an idea never build it.

**What users can make**

- 3D-printable objects: functional parts, gifts, figurines, replacement parts from a photo, cosplay and miniatures, molds.
- Electronics projects: circuit, schematic, PCB, firmware, simulation, parts list, assembly guide.
- Enclosures generated to fit the exact board, ports, buttons and screens.
- Smart home devices and robots: electronics, mechanics, firmware and case together.
- Laser-cut and CNC parts: flat-pack furniture, boxes, signs, stencils.
- Companion apps: a web app (PWA) that controls the device over Bluetooth or Wi-Fi.
- Product prototypes for small businesses and inventors.

**How it gets made.** Users download files, order a print or PCB, buy a parts kit, or hire a nearby maker from the network. Designs can be published and sold on the marketplace. Schools buy STEM kits with lesson plans.

**Success metrics (first 12 months)**

| Metric | Target |
| --- | --- |
| Builds that pass all verification checks on first agent run | ≥ 70% |
| Median time from prompt to verified 3D design | < 3 minutes |
| Median time from prompt to verified electronics project | < 15 minutes |
| Users who order, download or publish within 7 days of signup | ≥ 30% |
| Physical orders that arrive and work as designed (user-confirmed) | ≥ 90% |
| Monthly paying subscribers | Set after pricing tests |

## 2. Users and personas

| Persona | Who | Main job | Pays for |
| --- | --- | --- | --- |
| Hobbyist | Makers, tinkerers, owners of a 3D printer or Arduino | Turn ideas into working gadgets fast | Subscription, kits |
| Student | University and secondary students, project teams | Final-year and class projects that work | Credits, kits |
| Everyday consumer | No technical skill | Gifts, replacement parts, home fixes | Per-order printing and delivery |
| Small business | Sellers, product startups, inventors | Prototypes, molds, packaging, branded products | Business plan, orders |
| Maker (supply side) | Owners of printers, laser cutters, soldering skills | Earn from local jobs | Commission taken from payouts |
| Designer (supply side) | Users who publish designs | Sell designs on the marketplace | Commission taken from sales |
| School | STEM teachers, administrators | Ready-made projects with lesson plans | Bulk kits, school licences |
| Admin | Internal team | Moderate, support, manage partners | — |

## 3. Scope

Everything below is in scope. The build order in section 15 sequences the work so each phase ships something usable and the next phase builds on it.

**Creation**

1. 3D object generation (functional, code-CAD).
2. Organic and artistic 3D generation (text-to-3D, image-to-3D).
3. Replacement part from a photo.
4. Molds generated from a model.
5. Lithophanes and personalized gifts.
6. Electronics project generation: requirements, components, schematic, PCB, Gerbers.
7. Firmware generation, compilation and simulation.
8. Enclosure generation from the PCB.
9. Smart home devices (electronics + firmware + enclosure + app as one project).
10. Robots and moving mechanisms.
11. Laser-cut and CNC designs (SVG, DXF).
12. Companion app generation (PWA with Web Bluetooth and Web Serial).
13. Product prototype mode for businesses.

**Verification**

14. Printability checker.
15. Electrical rule checks, design rule checks, power and thermal sanity checks.
16. Firmware compile and simulation checks.

**Making and commerce**

17. Downloads in every standard format.
18. Print ordering through partners and the maker network.
19. PCB and assembly ordering through fab partners.
20. Parts sourcing with live prices, and own-brand kits.
21. Step-by-step assembly guides with diagrams.
22. Maker network: onboarding, job matching, escrow, payouts, ratings.
23. Design marketplace: publish, sell, remix, licences.
24. STEM kits and school portal.

**Platform**

25. Accounts, teams, projects, versions, sharing, comments.
26. Subscriptions, credits, payments, payouts.
27. Admin console, moderation, support tools.
28. Public site with SEO marketplace pages.

**Platforms.** Web app first. iOS and Android apps follow (section 15), sharing the API and the TypeScript domain package. The mobile apps add camera capture for photo-to-part, push notifications for orders, and device control.

## 4. Tech stack (locked)

The stack is TypeScript on the client and Python on the server, because every CAD, EDA and firmware tool the agents drive has a Python or command-line interface. Pin exact versions in the repo at project start and record them in `docs/decisions/`.

| Layer | Choice | Why |
| --- | --- | --- |
| Studio web app | React + TypeScript + Vite | Fast dev loop, large ecosystem |
| Routing and server state | TanStack Router + TanStack Query | Type-safe routes, caching, optimistic updates |
| UI | Tailwind CSS + shadcn/ui | Consistent components, easy theming |
| 3D viewer | react-three-fiber + drei (three.js) | Rotate, section, measure, compare versions |
| Circuit and PCB viewer | KiCad-exported SVG + interactive overlay | Exact render of the real design files |
| Public site and marketplace | Astro (server-rendered) | SEO for listings, fast static pages |
| Mobile apps (later phase) | React Native + Expo | Shares TypeScript types and API client |
| API | FastAPI (Python), Pydantic v2 | Typed contracts, async, OpenAPI for codegen |
| Agent orchestration | LangGraph with Postgres checkpointer | Durable long runs, retries, human approval pauses |
| LLM access | Own model gateway (`Backend/llm`) over provider SDKs | Model-agnostic, per-task routing, fallback, cost tracking |
| Job queue | Redis + ARQ | Async Python workers, simple to operate |
| Realtime | Server-Sent Events for run progress, WebSockets for collaboration | Streams agent steps to the browser |
| Sandboxes | Container sandboxes behind an interface (E2B or Modal first, self-hosted Firecracker later) | Agent-written code never runs on core servers |
| Code-CAD | build123d (CadQuery kernel, OpenCascade) | Exact, parametric, exports STEP, STL, 3MF, DXF |
| Organic 3D | Text-to-3D and image-to-3D providers behind an interface | Swappable as quality improves |
| Mesh tools | trimesh, manifold3d | Repair, booleans, wall-thickness and overhang analysis |
| Slicing | PrusaSlicer CLI, CuraEngine | Real print time, filament use, failure warnings |
| Circuit generation | SKiDL (netlist as Python) and atopile | Agent writes circuits as code |
| PCB | KiCad CLI and Python API, Freerouting autorouter | Schematic, layout, DRC, Gerbers, BOM, pick-and-place |
| Firmware | PlatformIO (ESP32, Arduino, RP2040) | One build system for many boards |
| Simulation | Wokwi (CI/API), ngspice for analog checks | Test firmware and circuits before anything is built |
| Database | PostgreSQL 16 + pgvector | Relational core, semantic component search |
| Object storage | Amazon S3, served through Cloudflare | Design files, renders, firmware binaries |
| Auth | Clerk | Orgs and teams, social login, mobile SDKs |
| Payments | Paystack + Flutterwave (local), Stripe (international, Connect for payouts) | Local cards, bank transfer, mobile money, global cards |
| Search | Postgres full-text + pgvector, Meilisearch for marketplace | Fast faceted search |
| Email and notifications | Resend (email), Expo push (mobile), in-app inbox | Order and build updates |
| Observability | LangSmith (agent traces), Sentry, OpenTelemetry + Grafana | Debug agent runs, errors, performance |
| Hosting | AWS (ECS Fargate, RDS, ElastiCache, S3) + Cloudflare (DNS, CDN, WAF, Pages for Astro) | Mature managed services, global edge |
| Infrastructure as code | Terraform | Reproducible environments |
| CI/CD | GitHub Actions | Tests, image builds, deploys |
| Local dev | Docker Compose | One command to run everything |

**Region.** Primary AWS region eu-west-1 (Ireland), with Cloudflare at the edge. Latency from West Africa to Europe is usually lower than to Cape Town because of undersea cable routing. Measure before launch and move to af-south-1 if it wins (section 16).

## 5. System architecture

The API never runs a build itself: it validates the request, queues a run, and streams progress back while workers and sandboxes do the work.

&#91;embedded content: system architecture · clients, API, workers, engines\]

A run flows like this: the studio posts a prompt; the API stores it and enqueues a job; an agent worker runs the LangGraph build, calling the LLM gateway for reasoning and engine sandboxes for every CAD, EDA, firmware and simulation step. Sandboxes write files to S3; workers save checkpoints and results to Postgres and publish events to Redis, which the API streams to the browser over SSE.

## 6. Agent system

One LangGraph supervisor graph runs every build. It turns a prompt into a written spec, hands work to specialist subgraphs, verifies every output with real tools, and pauses for the user at fixed approval points. No output reaches the user as "done" until its verifiers pass.

**Build pipeline**

1. **Intake:** classify the request (object, electronics, device, robot, laser, app, mixed), extract constraints, ask up to 3 clarifying questions if critical facts are missing (size, power source, budget, target printer or material).
2. **Spec writer:** produce a structured `ProjectSpec` (JSON, schema in `Backend/schemas`): requirements, dimensions, interfaces, components, budget, success criteria. **Approval gate 1:** user confirms or edits the spec.
3. **Planner:** split the spec into tasks with dependencies (for example circuit → PCB → enclosure → app).
4. **Specialist subgraphs** run, in parallel where the dependencies allow:
   - Mechanical agent (code-CAD parts, assemblies, mechanisms)
   - Organic 3D agent (artistic shapes, combined with functional parts)
   - Electronics agent (components, netlist, schematic, PCB)
   - Firmware agent (code, build, simulate)
   - Enclosure agent (case from PCB geometry)
   - Fabrication agent (laser and CNC outputs)
   - App agent (companion PWA)
   - Docs agent (assembly guide, BOM, wiring diagrams)
5. **Verifiers:** each output runs its tool checks (section 7). A failure returns the error output to the specialist, up to 5 repair loops, then escalates to the user with a plain explanation.
6. **Integrator:** checks cross-part fit (board fits case, ports align, battery fits, mounting holes match) and assembles the project bundle.
7. **Costing:** parts, print, PCB and shipping quotes. **Approval gate 2:** user reviews before any order or payment.
8. **Delivery:** files saved, viewer updated, order flow offered.

**Edits.** A follow-up prompt ("make it 5 mm taller", "add a buzzer") reruns only the affected subgraphs, using the dependency graph, and creates a new project version.

**State and durability**

- State lives in a typed `BuildState` with the spec, task graph, artifacts (file references, never file contents) and verifier results.
- The Postgres checkpointer saves state after every node, so a run survives worker restarts and resumes after approval pauses that may last days.
- Every node emits progress events (`node_started`, `artifact_created`, `check_passed`, `check_failed`, `needs_approval`) to Redis, streamed to the browser over SSE.

**Tools agents can call** (each a typed Python function, executed inside the sandbox)

- `run_cad(script)` → STEP, STL, 3MF, renders, measurements
- `generate_mesh(prompt | image)` → mesh
- `check_printability(mesh, printer_profile)` → report
- `slice(mesh, profile)` → print time, material, warnings
- `search_components(query, constraints)` → parts with price and stock
- `build_netlist(skidl_script)` → netlist and ERC report
- `layout_pcb(netlist, board_constraints)` → KiCad project, DRC report, Gerbers
- `build_firmware(project)` → binary, compile log
- `simulate(firmware, circuit)` → simulation log and pass or fail per test
- `build_app(spec)` → PWA bundle and preview URL
- `render(asset)` → images for the UI and guides

**Model-agnostic LLM layer** (`Backend/llm`)

- One interface: `complete`, `stream`, `structured(schema)`, `tool_call`, `vision`.
- Adapters per provider, configured by environment, with no provider code anywhere else.
- A routing table maps each agent role to a model tier (planning and spec: strongest; repair loops and small edits: cheaper; vision: vision-capable). Swappable without code changes.
- Automatic fallback to a second provider on errors or timeouts.
- Token and cost logging per run, per user and per project, feeding credits and billing.
- An evaluation suite (`evals/`) of 200+ reference prompts with expected checks, run in CI on any model or prompt change.

## 7. Making engines

Each engine is a Python package in `engines/` with a typed input, a typed output and its own verifier. Agents call engines; engines never call LLMs. This keeps every engine testable without a model.

| Engine | Input | Output | Verifier must pass |
| --- | --- | --- | --- |
| Mechanical (code-CAD) | build123d script | STEP, STL, 3MF, PNG renders, dimensions | Script runs, solid is valid and watertight, dimensions within ±0.1 mm of spec |
| Organic 3D | Text prompt or image | Repaired mesh (GLB, STL) | Manifold, triangle count under limit, scaled to spec size |
| Hybrid | Organic mesh + CAD parts | Combined solid | Boolean succeeds, functional features intact |
| Photo-to-part | 1–6 photos + one reference measurement | Parametric CAD model | User confirms key dimensions before print |
| Mold | Positive model | Two-part mold with sprue, vents, keys | Draft angles present, parts separate cleanly |
| Lithophane and gifts | Photo or text | Printable relief model | Thickness range within printer profile |
| Printability | Mesh + printer profile + material | Report: walls, overhangs, bridges, supports, bed fit, orientation | No blocking errors; warnings shown to user |
| Slicing | Mesh + profile | G-code (optional), time, grams, cost | Slicer exits cleanly |
| Electronics | Component list + SKiDL script | Netlist, schematic (SVG, PDF), BOM | ERC clean, every part in stock or with substitute, power budget within supply |
| PCB | Netlist + board outline | KiCad project, Gerbers, drill, pick-and-place | DRC clean against fab rules for the chosen fab |
| Firmware | Board + pin map + behaviour spec | PlatformIO project, binary | Compiles with zero errors; pin map matches netlist |
| Simulation | Firmware + circuit | Test log | All behaviour tests from the spec pass in Wokwi |
| Enclosure | PCB 3D model + ports + user style | Printable case (two parts or more), fasteners | Board fits with 0.3 mm clearance, every port and button has an opening, screws match holes |
| Mechanism | Motion spec (gears, hinges, linkages) | Assembly + motion preview | No collisions across the motion range |
| Laser and CNC | 2D or flat-pack spec + material thickness | SVG, DXF, nesting layout | Closed paths, kerf applied, fits sheet size |
| Companion app | Device spec + firmware protocol | PWA (React) with Web Bluetooth, Web Serial or Wi-Fi control | Builds, connects to simulated device, all controls send correct messages |
| Assembly guide | Project bundle | Step list with renders, wiring diagrams, tools needed, PDF | Every part in BOM appears in a step |

**Printer and material profiles.** Ship profiles for common printers (Prusa, Bambu Lab, Creality, Elegoo) and materials (PLA, PETG, ABS, TPU, resin). Users can add their own.

**Component library.** A curated library of 2,000+ common parts (boards, sensors, motors, displays, regulators, connectors) with footprints, 3D models, pin maps and verified wiring notes, stored in Postgres with pgvector embeddings. Live price and stock come from parts APIs. The electronics agent prefers library parts and flags anything outside it.

**Firmware protocol contract.** Firmware and companion app share a generated message schema (JSON over BLE GATT or WebSocket), so the app agent never guesses what the device understands.

## 8. Features and acceptance criteria

Each feature lists the user story and the checks that define done. Claude Code should write an automated test for every criterion that can be automated.

### 8.1 Studio (the main workspace)

*As a user, I describe what I want and watch it get designed, then refine it by chatting or by editing values directly.*

- Three-panel layout: chat and build log (left), viewer (centre), properties and files (right). Collapses to tabs below 768 px width.
- Prompt box accepts text, images (up to 6) and voice notes (transcribed).
- Live build log shows each agent step as it runs, with checks passed and failed.
- Viewer switches between 3D model, schematic, PCB (top and bottom), firmware code, app preview and assembly guide.
- 3D viewer supports orbit, zoom, section planes, measure tool, explode view for assemblies, and side-by-side version compare.
- Parameters panel exposes the spec's key dimensions as sliders and inputs; changing one reruns only the affected engine, no LLM call needed for pure parameter changes.
- Every change creates a version; users can restore any version.

**Done when:** a user with no CAD knowledge can go from prompt to a verified, downloadable phone stand in under 3 minutes; parameter edits re-render in under 10 seconds; the build log never shows "done" while a verifier is failing.

### 8.2 3D objects

- Functional objects built with code-CAD; organic shapes built with the organic engine; hybrids combine both.
- Photo-to-part: user uploads photos of a broken part with a coin, ruler or a typed measurement for scale; the model is shown with editable key dimensions before print.
- Molds, lithophanes, name keychains and figurines available as templates on the home screen.
- Printability report shown before download or order, with one-click fixes (reorient, thicken walls, add supports, split for bed size).

**Done when:** 90% of the 100 reference object prompts in `evals/objects` produce watertight, printable models; photo-to-part gets key dimensions within ±0.5 mm on the 30 reference parts after one user correction.

### 8.3 Electronics and devices

- From a behaviour description ("water my plants when the soil is dry, alert my phone") the system proposes a board, components, power source and cost. User approves the spec.
- Outputs: schematic, PCB, BOM with live prices, firmware, simulation results, wiring diagram, enclosure and companion app.
- Breadboard mode: for beginners, a wiring guide using development boards and jumper wires instead of a custom PCB.
- Safety rules: mains voltage (above 50 V AC), high-current batteries and heating elements trigger warnings, require user acknowledgement, and are blocked for kits sold to schools.

**Done when:** 70% of the 100 reference device prompts in `evals/devices` pass ERC, DRC, compile and simulation on the first run, and 90% after repair loops; every BOM part has stock or a listed substitute.

### 8.4 Enclosures

- Generated from the PCB's 3D model or from a development board in the library.
- Styles: minimal, rounded, rugged, wall-mount, desk, wearable; user can upload a reference image for style.
- Openings for every connector, button, LED, screen and sensor that needs exposure; mounting bosses matching board holes; snap-fit or screw lid.

**Done when:** in the 50 reference enclosure tests, the board fits with clearance and every exposed component has an aligned opening, checked by geometry tests, not by eye.

### 8.5 Robots and mechanisms

- Gears, hinges, linkages, wheels and servo mounts from the mechanism engine.
- Motion preview animates the assembly through its range and highlights collisions.
- Robot templates: 2-wheel rover, 4-DOF arm, walking toy, pan-tilt camera mount.

**Done when:** each template builds, passes collision checks, and its firmware drives the motors correctly in simulation.

### 8.6 Laser and CNC

- Flat-pack boxes, furniture, signs and stencils from a description and material thickness.
- Finger joints, kerf compensation, sheet nesting, engraving layers.

**Done when:** outputs open without errors in common laser software, and a reference box assembles from a real cut test.

### 8.7 Companion apps

- Generated PWA with the device's controls (switches, sliders, charts of sensor data, schedules).
- Connects over Web Bluetooth or Web Serial in supported browsers, or over Wi-Fi through the device's local WebSocket.
- Users can restyle it by chat and install it to their phone home screen.

**Done when:** the app connects to the simulated device and every control round-trips correctly in automated tests.

### 8.8 Orders, kits and fabrication

- Order a print (material, colour, quantity), a PCB (bare or assembled), a parts kit, or a full project kit.
- Quotes combine partner prices, maker bids, shipping and fees, shown before payment.
- Order tracking with status, photos from the maker, and dispute flow.

**Done when:** a user can pay for and track an order end to end in staging with test payments; every order state change sends a notification.

### 8.9 Maker network

- Makers apply with equipment list, materials, location and sample photos; admins approve.
- Jobs are matched by distance, equipment, rating and price; makers accept or bid within a time window.
- Payment held in escrow, released on delivery confirmation or after 72 hours without a dispute.
- Ratings for both sides; maker dashboard with jobs, earnings and payouts.

**Done when:** matching, escrow, release, dispute and payout all work in staging with test payments and test accounts.

### 8.10 Marketplace

- Users publish designs as free, paid, or remixable; licences: personal, commercial, CC variants.
- Listing pages are server-rendered on the public site with renders, specs, BOM and reviews.
- "Make this" button opens the design in the studio or starts an order.
- Remixes keep attribution links to the original.

**Done when:** listings are indexable (valid sitemap and structured data), purchases grant access to files, and sellers see earnings.

### 8.11 Schools and STEM kits

- Catalogue of projects by age and subject with lesson plans, slides, worksheets and assessment rubrics.
- School accounts: teacher dashboard, class rosters, student project tracking, bulk kit ordering with invoices.

**Done when:** a teacher can create a class, assign a project, see student progress, and order 30 kits on one invoice.

### 8.12 Accounts, teams and sharing

- Sign up with email, Google or Apple; organizations with roles (owner, admin, member, viewer).
- Share a project by link (view, comment, edit); comments pinned to 3D positions or schematic parts.

**Done when:** permission tests cover every role and resource type.

### 8.13 Admin console

- Users, projects, orders, makers, listings, payouts, refunds, disputes, moderation queue, model cost dashboard, feature flags.

**Done when:** support staff can resolve a dispute, refund an order and suspend a listing without database access.

## 9. Data model

Postgres is the source of truth; files live in S3 and tables store only their keys and hashes. All tables have `id` (UUID v7), `created_at`, `updated_at`. Money is stored as integer minor units plus an ISO currency code. Migrations use Alembic.

| Table | Key fields | Notes |
| --- | --- | --- |
| `users` | clerk\_id, email, name, country, locale, role | Synced from Clerk webhooks |
| `organizations` | name, type (personal, business, school, maker) |  |
| `memberships` | user\_id, org\_id, role | owner, admin, member, viewer |
| `projects` | org\_id, owner\_id, title, kind, visibility, current\_version\_id, forked\_from\_id | kind: object, device, robot, laser, app, mixed |
| `project_versions` | project\_id, number, spec (JSONB), parent\_version\_id, created\_by\_run\_id | Immutable once created |
| `artifacts` | version\_id, type, format, s3\_key, sha256, size, metadata (JSONB) | type: model, mesh, schematic, pcb, gerbers, firmware, app, guide, render, bom |
| `agent_runs` | project\_id, version\_id, status, trigger\_prompt, model\_usage (JSONB), cost\_minor, started\_at, finished\_at | status: queued, running, awaiting\_approval, failed, succeeded, cancelled |
| `run_events` | run\_id, seq, type, payload (JSONB) | Append-only; replayed for the build log |
| `checks` | run\_id, artifact\_id, engine, name, status, report (JSONB) | pass, warn, fail |
| `approvals` | run\_id, gate, status, decided\_by, decided\_at, notes | gate: spec, order |
| `components` | mpn, manufacturer, category, specs (JSONB), footprint\_ref, model\_3d\_ref, embedding (vector), verified | Curated library |
| `component_offers` | component\_id, supplier, price\_minor, currency, stock, fetched\_at | Cached from parts APIs |
| `printer_profiles` | org\_id (null = system), brand, model, bed\_xyz, nozzle, settings (JSONB) |  |
| `materials` | name, process, properties (JSONB), cost\_per\_gram\_minor |  |
| `makers` | org\_id, status, location (PostGIS point), radius\_km, equipment (JSONB), rating, payout\_account\_ref | Requires PostGIS |
| `orders` | buyer\_org\_id, project\_version\_id, type, status, quote (JSONB), total\_minor, currency, shipping\_address\_id | type: print, pcb, kit, laser, maker\_job |
| `order_items` | order\_id, kind, ref\_id, quantity, unit\_price\_minor |  |
| `maker_jobs` | order\_id, maker\_id, status, bid\_minor, accepted\_at, delivered\_at |  |
| `payments` | order\_id, provider, provider\_ref, status, amount\_minor, currency | Paystack, Flutterwave, Stripe |
| `escrow_holds` | payment\_id, amount\_minor, release\_at, status |  |
| `payouts` | payee\_org\_id, provider, amount\_minor, status, provider\_ref |  |
| `disputes` | order\_id, opened\_by, reason, status, resolution |  |
| `listings` | project\_version\_id, seller\_org\_id, price\_minor, licence, status, slug |  |
| `purchases` | listing\_id, buyer\_org\_id, payment\_id | Grants file access |
| `reviews` | target\_type, target\_id, author\_id, rating, body | Listings and makers |
| `subscriptions` | org\_id, plan, provider, status, period\_end |  |
| `credit_ledger` | org\_id, delta, reason, run\_id, balance\_after | Append-only |
| `comments` | project\_id, version\_id, anchor (JSONB), author\_id, body, resolved | anchor: 3D point, schematic ref, PCB ref |
| `classes`, `class_members`, `assignments` | school org, teacher, students, project template |  |
| `kits` | sku, project\_template\_id, bom (JSONB), price\_minor, stock |  |
| `addresses` | org\_id, fields, verified |  |
| `notifications` | user\_id, type, payload, read\_at |  |
| `audit_log` | actor\_id, action, target, metadata | Admin and money actions |

## 10. API design

REST over JSON at `/v1`, documented by FastAPI's OpenAPI schema, with a generated TypeScript client in Frontend/`packages/api-client`. Auth is a Clerk JWT in the `Authorization` header. Lists use cursor pagination. Every mutating endpoint accepts an `Idempotency-Key` header.

| Method and path | Purpose |
| --- | --- |
| `POST /v1/projects` | Create a project from a prompt and attachments; starts a run |
| `GET /v1/projects/{id}` | Project with current version and artifacts |
| `POST /v1/projects/{id}/runs` | Start an edit run from a follow-up prompt |
| `PATCH /v1/projects/{id}/parameters` | Parameter-only change; reruns engines without an LLM |
| `GET /v1/runs/{id}/events` | SSE stream of run events, resumable with `Last-Event-ID` |
| `POST /v1/runs/{id}/approvals/{gate}` | Approve, edit or reject a spec or order gate |
| `POST /v1/runs/{id}/cancel` | Cancel a run |
| `GET /v1/projects/{id}/versions` | Version history; `POST …/versions/{v}/restore` restores |
| `GET /v1/artifacts/{id}/download` | Signed S3 URL, 10-minute expiry |
| `POST /v1/uploads` | Signed upload URL for images and reference files |
| `GET /v1/components/search` | Semantic and filtered component search |
| `POST /v1/quotes` | Quote a print, PCB, kit or maker job for a version |
| `POST /v1/orders` | Create an order from a quote; returns payment initialization |
| `GET /v1/orders/{id}` | Order with status timeline |
| `POST /v1/webhooks/{provider}` | Paystack, Flutterwave, Stripe, Clerk, fab partners; signature verified |
| `GET /v1/maker/jobs` and `POST /v1/maker/jobs/{id}/accept` | Maker job feed and acceptance |
| `POST /v1/listings` and `GET /v1/listings/{slug}` | Publish and view marketplace listings |
| `POST /v1/disputes` | Open a dispute |
| `GET /v1/me/credits` | Credit balance and ledger |
| `/v1/admin/*` | Admin actions, role-gated and audit-logged |

**Run event types:** `run_started`, `node_started`, `node_finished`, `artifact_created`, `check_passed`, `check_warned`, `check_failed`, `repair_attempt`, `needs_input`, `needs_approval`, `cost_update`, `run_finished`, `run_failed`.

## 11. Safety, security and compliance

**Content safety (design policy).** A policy classifier runs at intake and again on the final spec. The system refuses, with a short explanation:

- Weapons, weapon parts and accessories (firearm components, suppressors, magazines, knives designed as weapons), explosives and their components.
- Devices for covert surveillance, tracking people without consent, or intercepting communications.
- Lock-bypass and skimming devices, and anything designed to defeat security systems.
- Medical devices that make treatment claims; regulated products presented as certified.

Refused requests are logged for review. Marketplace listings pass the same classifier plus human moderation before publishing. Makers can decline any job and report it.

**Physical safety.**

- Mains voltage, lithium battery packs above a set capacity, heating elements, motors above a set torque, and lasers above Class 2 trigger warnings and required acknowledgement; designs for schools block them.
- Every electronics guide includes a safety section generated from the design (polarity, fusing, battery handling, ventilation).
- Products are sold as hobby and educational builds, not certified consumer electronics. Terms of service state this; legal review required before launch.

**Platform security.**

- Agent-written code runs only in sandboxes: no network except an allowlist (package mirrors, parts APIs), CPU and memory limits, 10-minute timeout, destroyed after each job.
- Uploaded files are scanned, size-limited and type-checked; images are re-encoded.
- Prompt-injection defence: content from uploads, web pages and part datasheets is treated as data; it never changes tool permissions or approval gates.
- Secrets in AWS Secrets Manager; no secrets in sandboxes.
- Signed, short-lived URLs for all file access; private projects are never served publicly.
- Rate limits per user and per IP; credit checks before each run.
- Payments: no card data touches our servers (provider-hosted checkout); all webhooks verified by signature; money actions recorded in `audit_log`.

**Privacy and compliance.**

- Comply with the Nigeria Data Protection Act 2023 and GDPR: consent records, data export, account deletion within 30 days, data processing agreements with every vendor.
- Location of makers shown only as approximate distance until a job is accepted.
- KYC for makers and sellers before payouts, through the payment providers.
- Import, customs and electronics shipping rules checked per destination before launching physical orders in each country.

## 12. Payments and economics

Revenue comes from five streams; all prices below are starting assumptions to test, stored as config, not code.

| Stream | Model | Starting assumption |
| --- | --- | --- |
| Subscriptions | Free, Maker, Pro, Business, School plans with monthly credits | Free tier: 3 builds a month, STL downloads only |
| Credits | Pay-as-you-go top-ups; each run costs credits based on model usage and engine compute | Credit price set to keep gross margin above 60% on compute |
| Orders | Margin on prints, PCBs, kits and laser jobs through partners | 15–25% on partner cost |
| Maker network | Commission on each completed job | 15% from the maker payout, plus a buyer service fee |
| Marketplace | Commission on paid design sales | 15–20% of sale price |

**Payment routing.**

- Users in Nigeria and other supported African countries: Paystack by default, Flutterwave as fallback; cards, bank transfer, USSD and mobile money where available.
- International users: Stripe.
- Payouts to makers and sellers: Paystack transfers or Flutterwave payouts locally, Stripe Connect internationally.
- Prices shown in the user's local currency; exchange rates refreshed daily and locked at quote time for 30 minutes.

**Escrow flow.** Buyer pays → funds held → maker accepts and fulfils → buyer confirms delivery (or 72 hours pass without a dispute) → payout minus commission. A dispute freezes the hold until an admin resolves it.

## 13. Non-functional requirements

| Area | Requirement |
| --- | --- |
| API latency | p95 under 300 ms for non-run endpoints |
| Run start | First progress event within 3 seconds of submit |
| Viewer | 3D model of 500k triangles loads in under 3 seconds on a mid-range Android phone over 4G; meshes served as compressed GLB (Draco) |
| Low bandwidth | Studio usable at 1 Mbps; renders and previews progressively loaded |
| Availability | 99.9% for API and studio; agent workers degrade gracefully (queue, never drop) |
| Scale | 1,000 concurrent runs at launch, workers autoscale on queue depth |
| Durability | Daily database backups with point-in-time recovery for 14 days; S3 versioning on artifacts |
| Accessibility | WCAG 2.2 AA for all non-3D UI; 3D viewer has keyboard controls and text descriptions of models |
| Localization | English at launch; strings externalized for French, Hausa, Yoruba, Igbo, Swahili, Arabic later |
| Browser support | Last 2 versions of Chrome, Edge, Safari, Firefox; Web Bluetooth features flagged where unsupported |
| Cost control | Per-run cost cap; runs that exceed it pause and ask the user |
| Testing | 80% line coverage on engines and API; Playwright end-to-end tests for core flows; nightly eval suite |

## 14. Repo structure and conventions for Claude Code

Two top-level folders: `Frontend/` for all frontend work (pnpm workspace, TypeScript) and `Backend/` for all backend work (uv workspace, Python). They talk only through the HTTP API and generated types; nothing imports across them.

```
kehora/
  Frontend/
    apps/
      studio/        React + Vite studio
      site/          Astro public site and marketplace
      admin/         Admin console
      mobile/        Expo app (later phase)
    packages/
      ui/            Shared React components
      viewer/        3D, schematic and PCB viewers
      api-client/    Generated TypeScript client (from OpenAPI)
      types/         Generated TypeScript types (from Backend/schemas)
  Backend/
    api/             FastAPI service (payments/adapters inside)
    agents/          LangGraph graphs, nodes, prompts, tool bindings
    engines/
      cad/  mesh/  printability/  slicing/  electronics/  pcb/
      firmware/  simulation/  enclosure/  mechanism/  laser/
      app_builder/  guides/
    engines_runner/  Sandbox job runner
    llm/             Model gateway and provider adapters
    schemas/         JSON Schemas, source of truth for shared shapes
    db/              Models and Alembic migrations
    data/            components, printer-profiles, materials, templates
    evals/           objects, devices, enclosures, mechanisms
    infra/           Terraform, Dockerfiles
    tests/
  docs/              PRD.md, decisions/ (ADRs)
  CLAUDE.md          Rules for Claude Code
  Makefile  docker-compose.yml  .github/
```

**Rules for `CLAUDE.md`**

- Frontend work stays in `Frontend/`, backend work in `Backend/`; never import across them.
- Schemas first: any new data shape is added to `Backend/schemas/` and generated for both sides with `make codegen`; never hand-write duplicate types.
- Engines are pure: no LLM calls, no network except declared APIs, fully unit-tested with fixture files.
- No provider SDK imports outside `Backend/llm/` and `Backend/api/payments/adapters/`.
- Every feature ships with tests matching its acceptance criteria in section 8.
- Every agent prompt lives in a versioned file under `Backend/agents/prompts/`, never inline.
- Run `make check` (lint, type check, tests) before every commit; CI runs the same plus evals on agent changes.
- Feature flags for every phase-gated feature, so unfinished work can merge to main.
- Write an ADR in `docs/decisions/` for any change to this stack.

## 15. Build order and milestones

Everything ships, in this order: each phase builds on the engines and platform of the one before, and the next phase starts only when its gate passes. Dates depend on team size (section 16).

&#91;embedded content: build order · 7 phases, 6 gates\]

Admin tools, security and tests grow inside every phase rather than waiting for the end. Work behind feature flags so later phases can merge early.

## 16. Open questions

- [ ] Product name and domain.
- [ ] Launch countries for physical orders (customs, shipping partners, payment coverage).
- [ ] AWS region: confirm eu-west-1 versus af-south-1 with latency tests from target cities.
- [ ] Which text-to-3D provider wins on quality and price at build time (run a bake-off of at least 3).
- [ ] PCB fab partners and whether their APIs support automated ordering.
- [ ] Parts data source licence terms (Octopart/Nexar or alternatives) for caching prices.
- [ ] Print partners per launch country, and how many makers to recruit before opening the network.
- [ ] Kit fulfilment: own warehouse, third-party logistics, or maker-assembled.
- [ ] Final pricing and credit costs after compute measurements in phase 1.
- [ ] Legal review: product liability, marketplace licences, terms of service, maker agreements.
- [ ] Team size and timeline, which set the dates on the build plan.
