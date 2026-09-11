# Operations and recovery

Deletion denies content access immediately. Remote journal acknowledgement is required before acceptance is reported. Online content is purged at the earlier of 30 days or a stricter license deadline; metadata without body text is retained for one year. Restores replay revocations and entitlement corrections before traffic is opened.

Backups must combine PostgreSQL/WAL, immutable-file manifests, and the remote journal watermark. Weekly full and incremental chains may not retain restricted bodies beyond the 30-day ceiling merely to widen restore history. A host-loss drill must show a common restore point, file hashes, license checks, side-effect reconciliation, measured data loss no greater than one hour, and measured recovery no greater than four hours. Until that drill exists, RPO/RTO status is `UNVERIFIED`.

Capacity acceptance uses three independent runs, five-minute warm-up and thirty-minute sampling. It covers project lists, record pagination/filtering, candidate details, task status and authorized graph neighborhoods under cold/warm caches for 10 accounts, 3 concurrent users, and 10 projects containing 2,000 records and 200 full texts each. Five-hundred errors, missing content, and permission faults count as failures.
