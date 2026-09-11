# Acceptance evidence register

Statuses separate static review, automated implementation tests, and real-pilot evidence. A missing real-world dependency remains `UNCONFIGURED` or `UNVERIFIED`; it is never converted into a pass.

| Scope | Automated evidence | Real evidence | Current status |
|---|---|---|---|
| S01–S04, S06–S10, S12, S14–S17, S19 | `platform/tests/`（当前自动化规则与API覆盖） | Required for actual platform data | IMPLEMENTED / PILOT_PENDING |
| S05, S07, S11, S13, S18 | Domain contract represented; persistent workflows incomplete | Required | PARTIAL |
| T01–T09, T12, T14, T17, T19–T20 | Contract and scenario tests | Fault injection still required | PARTIAL |
| T10, T11, T21 | Protocol documented in source architecture | Raw capacity and off-host recovery records absent | UNVERIFIED |
| Real ferroptosis/radioresistance pilot | Project fixture and dependency behavior only | Licensed exports, reviewers, and measurements absent | PILOT_PENDING |

## Evidence rules

Each execution record must identify the actor, object/version, input fingerprints, event order, expected and actual output, UTC time, and executor. Restricted text and model material must stay in the project evidence domain. CI receives synthetic or de-identified identifiers only.

自动化测试通过只证明当前实现的规则与接口行为，不代表整组场景的生产故障注入或真实材料验收已经完成。正式状态以本表的 `Current status` 和对应原始证据为准。
