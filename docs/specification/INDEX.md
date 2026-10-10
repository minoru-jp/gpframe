<!-- Published from devdocs/canonical_documents/specification/INDEX.md sha256:b9756544298d22294f9fd818648c17328ce09defb9d688501ef806e891e27301. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# gpframe Specification

| Document | Summary |
| --- | --- |
| [Session](session.md) | Rules on opening and closing sessions, spawning frames, judgement at exit, and sub-sessions. |
| [Frame](frame.md) | Rules on frame states, receiving return values and exceptions, and acknowledgement of failures. |
| [Stop](stop.md) | Rules on stop requests, how a stop propagates, and stop callbacks. |
| [Waiting](waiting.md) | Rules on how to wait for all frames to end and how to wait for the first failure. |
| [Shared](shared.md) | Rules on creating, reading, writing, and atomically updating Shared, a shared cell with a fixed type. |
| [Channel](channel.md) | Rules on Channel, which passes values between frames in order and whose send and receive waits are released by a stop request. |
