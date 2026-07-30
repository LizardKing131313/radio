## 1. Implementation

- [x] 1.1 Refresh search heartbeat during startup delay and regular/backoff sleep.
- [x] 1.2 Run the full regression and deployment manifest checks.

## 2. Acceptance

- [ ] 2.1 Deploy and confirm search restart count remains stable beyond 15 minutes while the next search tick is
  pending.
- [ ] 2.2 Archive the change after production acceptance.
