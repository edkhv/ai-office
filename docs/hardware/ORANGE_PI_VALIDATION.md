# Orange Pi hardware validation plan

Status: **Target hardware; not yet validated on device.** Target from owner brief: Orange Pi AI Studio Pro, 96 GB configuration. This is not an assertion about how that memory is exposed to software.

No device was attached or tested. No drivers, firmware, CANN, MindIE, vLLM-Ascend or torch_npu were installed by this project. The software image was tested on a Docker Linux ARM64 VM on an Apple Silicon development host and on Linux x86_64 in GitHub Actions. These are independently built images, not a published multi-architecture image distribution or proof of Orange Pi compatibility.

| Gate | Required evidence / question | Current result |
|---|---|---|
| Identity | Exact SKU, board/SoC/revision, vendor product documentation | Pending |
| Memory | Physical partitioning, usable pools, unified-address support, reservations | Pending; no inferred 96 GB shared pool |
| Boot / OS / storage | Supported OS image, boot procedure, on-board storage, model placement | Pending |
| Host topology | Standalone versus host-assisted operation, supported host OS, cables | Pending |
| USB4 / transport | Actual transport protocol; whether networking is available | Pending; USB4 is not presumed HTTP |
| Driver stack | Firmware/driver/CANN versions, installation and rollback | Pending |
| Runtime | Exact supported MindIE/vLLM-Ascend/other version and HTTP contract | Pending |
| Models | Architecture, quantization, format, conversion tools, license | Pending |
| Thermal / power | Cooling, sustained load, power draw, graceful shutdown | Pending |
| Failure recovery | Power cut, boot after outage, persisted data and model reload | Pending |
| Business test | Same approved-workflow and evidence tests on the physical device | Not run |

First obtain official documentation and confirm transport. Boot a vendor-supported image without changing the development host. Record checksums, versions and exact settings. Validate `/models` and bounded generation without assuming tools, structured output or embeddings. Select one supported model, then measure cold/warm latency, throughput, peak memory, context length, concurrency, sustained thermals and power. Use fixed prompts plus repeated business cases and record both failures and successes. Report median/p95 only from an adequate sample. Test outage and recovery with approval from the hardware owner.

Record date/operator/SKU/OS/firmware/runtime/model/digest, test SHA, sample count, workload, token counts if available, duration, watts/temperature/memory if measured, and logs stripped of secrets. Unmeasured fields stay null. TOPS are not tokens/second; marketing figures are not benchmark results.

Primary starting references to obtain/recheck: [Orange Pi product page](https://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-AI-Studio-Pro.html), [vLLM-Ascend documentation](https://docs.vllm.ai/projects/ascend/en/latest/getting_started/installation.html). Links are leads, not support evidence for this SKU. The owner's reseller URL is not treated as an engineering specification. Physical results must be added before changing on_device status.
