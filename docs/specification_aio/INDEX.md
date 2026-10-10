<!-- Published from devdocs/canonical_documents/specification_aio/INDEX.md sha256:6435afea006f439960a00a9e95d5330c5565b1f39f034ec2e40c8198c0b4a95c. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# gpframe.aio Specification

| Document | Summary |
| --- | --- |
| [Constraints and limits](limits.md) | Defines up front what the asynchronous API cannot guarantee. The constraints users must follow, and the limits that gpframe.aio inherently cannot guarantee. |
| [Async frame](frame.md) | Rules on asynchronous frame states (succeeded / stopped / broken), receiving results, and acknowledgement of failures. |
| [Async session](session.md) | Rules on opening and closing asynchronous sessions, type separation from the synchronous API, spawning frames, judgement at exit, and sub-sessions. |
| [Async stop](stop.md) | Rules on stop requests and delivery of cancellation in the asynchronous API, how a stop propagates, and stop callbacks. |
| [Async waiting](waiting.md) | Rules on how, in the asynchronous API, to wait for all frames to end and for the first failure without stopping the event loop. |
| [Health monitoring](health.md) | Rules on the health check, which detects from outside the event loop that the event loop has stopped responding and reports it. An observation tool that lies outside the session's guarantees. |
