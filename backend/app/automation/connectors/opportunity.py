from __future__ import annotations

from app.automation.contracts import ConnectorCapability, ConnectorRejected, ConnectorRequest, ConnectorResult, ConnectorStatus


class OpportunityConnector:
    connector_id = "opportunity"

    def capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability("collect_observations", "Collect deterministic opportunity observations from configured fixtures.", {}),
            ConnectorCapability("ingest_observation", "Normalize and persist an opportunity observation through the API layer.", {}),
            ConnectorCapability("run_discovery", "Authorize deterministic opportunity discovery.", {}),
            ConnectorCapability("expire_opportunities", "Authorize deterministic opportunity expiration.", {}),
            ConnectorCapability("rank_opportunities", "Authorize opportunity ranking for the Creator.", {}),
            ConnectorCapability("review_opportunity", "Authorize Creator opportunity review.", {}),
            ConnectorCapability("convert_to_inception", "Authorize Creator conversion of an approved opportunity to Inception.", {}),
        ]

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.capability == "collect_observations":
            return ConnectorResult(
                status=ConnectorStatus.SUCCEEDED,
                output={
                    "observations": [
                        {
                            "universe": "finance",
                            "source": "fixture.market",
                            "subject": "ACME",
                            "event_type": "volume_anomaly",
                            "title": "ACME volume anomaly",
                            "summary": "Volume rose above the configured informational threshold.",
                            "source_reliability": 0.82,
                            "correlation_key": "ACME:volume",
                        }
                    ]
                },
            )
        if request.capability in {
            "ingest_observation",
            "run_discovery",
            "expire_opportunities",
            "rank_opportunities",
            "review_opportunity",
            "convert_to_inception",
        }:
            return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"authorized": True})
        raise ConnectorRejected("Unsupported opportunity capability")
