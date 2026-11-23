# Show events, alerts and incidents separately

Open http://localhost:5173/admin and log in as admin.

1. Enable **Step-by-step demo (pause before incidents)**.
2. Select **mirai_bruteforce** and click **1. Generate events**.
3. Scroll to **Events → Alerts → Incidents**. The selected run automatically opens; use **Inspect process** to reopen it later.
4. Expand a stored event. Explain: “This is one observation, such as a failed login. The API validates it, adds the per-device hash link, and stores it in the events collection.”
5. Wait for **awaiting correlation**. Expand a detected alert and show its ruleId, stage and eventIds. Explain: “MongoDB change streams notify the detector. The detector executes the rule's stored aggregation pipeline. A match creates an alert, and eventIds point to its evidence.” Detection happens automatically; there is no fake Generate Alerts button.
6. Point to **Correlated incidents · 0**. Explain: “We have evidence and suspicious findings. Presentation mode pauses incident creation so we can inspect them.”
7. Click **3. Build incident**, then **Open incident**. Explain: “MongoDB graph lookups connect related alerts. One transaction saves the incident, links its alerts and updates risk scores.”
8. Repeat with **lateral_movement** to show the multi-hop graph. Explain: “The target IP of one hop becomes the source IP of the next. Related alerts form one investigation, ordered by hop.”

For a Compass demonstration, expand **Show the same evidence in MongoDB Compass** below the three panels. Open the correct honeygraph database, select each named collection and paste its displayed filter into the Documents filter bar. The filters select this run's actual ObjectIds. Use alerts.eventIds and incidents.chain.alertId to trace the references. Refresh Documents after building the incident.

## What the terms mean

| Record | Simple explanation |
| --- | --- |
| Event | Something happened: for example, a login failed. |
| Alert | A detection rule found suspicious activity in one or more events. |
| Incident | Related alerts were connected into one investigation or attack chain. |

Say: “The simulator produces activity records. The system detects suspicious activity and reconstructs incidents from that evidence.”

## Verified run on 19 November 2026

| Scenario | Events | Alerts before building | Incidents before building | Incidents after building |
| --- | ---: | ---: | ---: | ---: |
| Mirai brute force | 18 | 10 | 0 | 1 |
| Lateral movement | 4 | 4 | 0 | 1 |

All four lateral hops appeared in order. Repeating the correlation request returned the existing incident. Alert counts depend on active rules, cooldowns and traffic; ten is the measured Mirai result with the current live rules, including previously added demonstration rules.

Automatic mode remains the default. It executes the same pipeline without the presentation pause. Only incident creation pauses in presentation mode: change-stream detection remains live. Do not run a separate chain-builder process against a paused run during the demonstration, because it can correlate those alerts independently.

Run metadata is held in the API process, as before. A backend restart clears the job cards; saved database evidence remains. Launch a fresh guided run after a restart. The evidence panel shows up to 200 documents per stage and counts from live queries; counts may advance while detection is still running. No matching alerts means no fabricated incident: check active rules or cooldown and launch another run.
