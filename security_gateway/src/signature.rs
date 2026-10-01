use hmac::{Hmac, Mac};
use sha2::Sha256;
use subtle::ConstantTimeEq;

use crate::contracts::ExecutionEnvelope;

type HmacSha256 = Hmac<Sha256>;

fn signing_message(e: &ExecutionEnvelope) -> String {
    format!(
        "{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
        e.protocol_version,
        e.run_id,
        e.execution_id,
        e.contract_hash,
        e.plan_hash,
        e.mission_id,
        e.mission_version,
        e.action_id,
        e.actor,
        e.target,
        e.environment,
        e.capability,
        e.action_class,
        e.risk_class,
        e.decision,
        e.decision_id,
        e.grant_id,
        e.expires_unix,
        e.nonce,
        e.parameters_hash,
        e.tool_id
    )
}

pub fn expected_signature(e: &ExecutionEnvelope, key: &[u8]) -> String {
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC accepts arbitrary key length");
    mac.update(signing_message(e).as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

pub fn verify_signature(e: &ExecutionEnvelope, key: &[u8]) -> bool {
    let expected = expected_signature(e, key);
    expected.as_bytes().ct_eq(e.signature.as_bytes()).into()
}
