## TRRF

### About

The Trial Ready Registry Framework (or TRRF) has been forked from the Rare Disease Registry Framework (or RDRF) by Queensland University of Technology's eResearch team in order to produce a trial ready framework that is fit for purpose across all diseases, with easy deployment, availability and efficient use.

RDRF has been developed at the [Centre for Comparative Genomics](http://ccg.murdoch.edu.au), Murdoch University, Western Australia.

The Rare Disease Registry Framework (RDRF) is an open source tool for the creation of web-based patient registries. What makes it unique is that data entry forms are based on reusable data element definitions (called "Common Data Elements" ) which can be created and/or loaded into the system at runtime. This means that registries can be created and modified without changes to the source code.

### Contact

Hosted on GitHub:

https://github.com/eresearchqut/trrf

Email:

[matthew.bellgard@qut.edu.au](mailto:matthew.bellgard@qut.edu.au)

### Database connections and availability checks

PostgreSQL connections use `DB_CONNECT_TIMEOUT=5` seconds per connection
attempt, for both the default and clinical databases. The timeout must be
positive. This bounds connection establishment, not SQL execution or the total
request duration. There is no automatic replay of requests or transactions.

Connection reuse remains disabled by default (`DB_CONN_MAX_AGE=0`). QA can
trial `DB_CONN_MAX_AGE=60`; reused connections are health-checked before use.
Keep the number of workers, threads, replicas, and database aliases in mind
when budgeting persistent connections. Negative connection ages are rejected.

- `/live`: unauthenticated, uncached process liveness; does not query databases.
- `/ready`: unauthenticated, uncached database readiness; checks both aliases,
  returning `{"success": true}` (200) or `{"success": false}` (503) for
  connection failures. Error details are not exposed. Each check logs its
  outcome for availability monitoring.
- `/health-check`: existing registry-count response, retained for compatibility.

Keep Front Door database-aware by probing `/ready`, not `/live`. Enable a
stateful consecutive-failure availability alert before suppressing individual
readiness notification emails with `READINESS_AGGREGATED_ALERTS_ENABLED=True`.
The default is false: emails remain enabled until that external alert is in
place. The filter only suppresses readiness 503 emails, not console logs,
other endpoints, unexpected exceptions, or any 500 response.

### Publications

**Please cite the following**:

Bellgard MI, Snelling T, McGree JM. RD-RAP: beyond rare disease patient registries, devising a comprehensive data and analytic framework. Orphanet J Rare Dis. 2019;14(1):176. Published 2019 Jul 12. doi:10.1186/s13023-019-1139-9

**Other relevant publications**:

Matthew I Bellgard, Lee Render, Maciej Radochonski and Adam Hunter, Second generation registry framework, Source Code Biol Med. 2014 Jun 20;9:14.

Matthew Bellgard, Christophe Beroud, Kay Parkinson, Tess Harris, Segolene Ayme, Gareth Baynam, Tarun Weeramanthri, Hugh Dawkins and Adam Hunter, Dispelling myths about rare disease registry system development. Source Code for Biology and Medicine, 2013. 8(1): p. 21.

Rodrigues M, Hammond-Tooke G, Kidd A, Love D, Patel R, Dawkins H, Bellgard M, Roxburgh R, The New Zealand Neuromuscular Disease Registry. J Clin Neurosci, 2012. 19(12): p. 1749-50.

Bellgard MI, Macgregor A, Janon F, Harvey A, O'leary P, Hunter A and Dawkins H, A modular approach to disease registry design: successful adoption of an internet-based rare disease registry. Hum Mutat 33: E2356-2366.
