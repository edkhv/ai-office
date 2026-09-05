# Local AI Station 96–128 GB — hardware validation plan

Status: **Target hardware; not yet validated on device.** The proposed configuration is a Local AI Station with 96–128 GB of memory. No manufacturer, processor architecture or accelerator is mandatory. Capacity is a selection range, not a claim that all memory is available to a model or that a workload will run at a given speed.

Development and software tests can continue on an available computer. The station may host the application and inference together, or use a separate management computer when required by the chosen configuration. A device-specific runtime and container build must be validated before delivery. The shared HTTP contract alone does not establish hardware compatibility.

No target station was attached or physically tested. No vendor driver or firmware was installed. The software image was tested on a Docker Linux ARM64 VM on an Apple Silicon host and on Linux x86_64 in GitHub Actions. These results are not certification of a station.

| Gate | Required evidence | Current result |
|---|---|---|
| Identity | Manufacturer, exact SKU, CPU/GPU/NPU, revision and official specifications | Pending; vendor not selected |
| Memory | Selected capacity in the 96–128 GB range, usable model memory, shared/dedicated topology and OS reserves | Pending |
| OS / storage | Supported OS, CPU architecture, containers, SSD capacity and model/data placement | Pending |
| Topology | Single station or additional host; required interfaces and cables | Pending; no mandatory separate host |
| Transport | Local/network inference endpoint, authentication and supported API | Pending; no interface presumed to provide HTTP |
| Driver stack | Exact driver/firmware/runtime versions, installation and rollback | Pending |
| Models | Architecture, quantization, format, license, context and embeddings | Pending |
| Thermal / power | Cooling, sustained load, power demand, UPS sizing and graceful shutdown | Pending |
| Connectivity | Router, permitted remote access and measured failover where included | Pending |
| Failure recovery | Power cut, cold boot, persisted data, model reload and isolated backup restore | Pending |
| Business test | The same approved-workflow and evidence tests on the chosen station | Not run |

Obtain manufacturer documentation and choose one supported configuration. Record checksums, versions and settings. Validate bounded generation and embeddings without assuming tool or structured-output support. Measure cold/warm latency, throughput, peak memory, context, concurrency, sustained thermals and power with repeated business cases. Record failures as well as successes; do not infer tokens/second from TOPS or memory capacity.

Each report records date/operator, SKU/OS/driver/runtime/model digest, code SHA, workload, sample count and measured results. Unmeasured fields stay null. Preserve reproducible installation and rollback instructions. Physical results must be recorded before changing device validation from `not_run`.
