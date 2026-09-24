use super::SandboxBackend;

pub fn select(
    configured: &str,
    kata_supported: bool,
    firecracker_supported: bool,
) -> Result<SandboxBackend, String> {
    match configured {
        "kata" if kata_supported => Ok(SandboxBackend::Kata),
        "firecracker" if firecracker_supported => Ok(SandboxBackend::Firecracker),
        "kata" | "firecracker" => Err("configured sandbox backend is unavailable".into()),
        "auto" if kata_supported => Ok(SandboxBackend::Kata),
        "auto" if firecracker_supported => Ok(SandboxBackend::Firecracker),
        "auto" => Ok(SandboxBackend::Unavailable),
        _ => Err("unknown sandbox backend".into()),
    }
}
