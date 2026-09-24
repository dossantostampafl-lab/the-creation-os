use crate::contracts::ExecutionEnvelope;

#[derive(Debug, PartialEq)]
pub enum Denial {
    Expired,
    WrongEnvironment,
    MissingDecision,
    MissingGrant,
    InvalidParametersHash,
}

pub fn validate(envelope: &ExecutionEnvelope, expected_environment: &str, now_unix: i64, actual_parameters_hash: &str) -> Result<(), Denial> {
    if envelope.expires_unix <= now_unix { return Err(Denial::Expired); }
    if envelope.environment != expected_environment { return Err(Denial::WrongEnvironment); }
    if envelope.decision_id.is_empty() { return Err(Denial::MissingDecision); }
    if envelope.grant_id.is_empty() { return Err(Denial::MissingGrant); }
    if envelope.parameters_hash != actual_parameters_hash { return Err(Denial::InvalidParametersHash); }
    Ok(())
}
