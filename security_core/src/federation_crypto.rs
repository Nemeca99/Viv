//! Native asymmetric primitives for the offline federation stage.
//!
//! This module deliberately owns only the cryptographic primitive.  It does
//! not open sockets, persist a node registry, emit telemetry, or decide
//! whether a node is trusted.  The Python federation registry owns protocol
//! admission; this Rust module supplies Windows CNG ECDSA P-256 signing and
//! verification plus DPAPI protection for a local private-key blob.
//!
//! The protected private-key blob is an opaque handoff between the local node
//! and this process.  It is bound to the Windows user/machine through DPAPI
//! and to the node identifier through additional entropy.  Callers must keep
//! it outside the repository and outside Master telemetry.

use hex::{decode as hex_decode, encode as hex_encode};
use serde::Serialize;
use sha2::{Digest, Sha256};

pub const FEDERATION_SIGNATURE_ALGORITHM: &str = "ECDSA_P256_SHA256_CNG";
pub const FEDERATION_SIGNATURE_HEX_BYTES: usize = 64;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct FederationKeyMaterial {
    pub algorithm: String,
    pub public_key_hex: String,
    pub public_key_sha256: String,
    pub node_identity_hash: String,
    pub protected_private_key_hex: String,
    pub private_key_scope: String,
}

fn sha256_bytes(value: &[u8]) -> Vec<u8> {
    Sha256::digest(value).to_vec()
}

fn sha256_hex(value: &[u8]) -> String {
    hex_encode(Sha256::digest(value)).to_uppercase()
}

fn node_entropy(node_id: &str) -> Vec<u8> {
    sha256_bytes(node_id.as_bytes())
}

fn validate_node_id(node_id: &str) -> Result<(), String> {
    if node_id.is_empty() || node_id.len() > 256 {
        return Err("federation_node_id_invalid".to_string());
    }
    Ok(())
}

#[cfg(windows)]
fn cng_failure(operation: &str, status: i32) -> String {
    format!("{operation}_failed:ntstatus={status}")
}

#[cfg(windows)]
fn dpapi_protect(plaintext: &[u8], entropy: &[u8]) -> Result<Vec<u8>, String> {
    use std::ptr;
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::Security::Cryptography::{
        CryptProtectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };

    let input = CRYPT_INTEGER_BLOB {
        cbData: plaintext.len() as u32,
        pbData: plaintext.as_ptr() as *mut u8,
    };
    let entropy_blob = CRYPT_INTEGER_BLOB {
        cbData: entropy.len() as u32,
        pbData: entropy.as_ptr() as *mut u8,
    };
    let mut output = CRYPT_INTEGER_BLOB {
        cbData: 0,
        pbData: ptr::null_mut(),
    };
    let ok = unsafe {
        CryptProtectData(
            &input,
            ptr::null(),
            &entropy_blob,
            ptr::null(),
            ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut output,
        )
    };
    if ok == 0 || output.pbData.is_null() {
        return Err("federation_dpapi_protect_failed".to_string());
    }
    let protected =
        unsafe { std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec() };
    unsafe {
        LocalFree(output.pbData as *mut core::ffi::c_void);
    }
    Ok(protected)
}

#[cfg(windows)]
fn dpapi_unprotect(ciphertext: &[u8], entropy: &[u8]) -> Result<Vec<u8>, String> {
    use std::ptr;
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::Security::Cryptography::{
        CryptUnprotectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };

    let input = CRYPT_INTEGER_BLOB {
        cbData: ciphertext.len() as u32,
        pbData: ciphertext.as_ptr() as *mut u8,
    };
    let entropy_blob = CRYPT_INTEGER_BLOB {
        cbData: entropy.len() as u32,
        pbData: entropy.as_ptr() as *mut u8,
    };
    let mut output = CRYPT_INTEGER_BLOB {
        cbData: 0,
        pbData: ptr::null_mut(),
    };
    let ok = unsafe {
        CryptUnprotectData(
            &input,
            ptr::null_mut(),
            &entropy_blob,
            ptr::null(),
            ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut output,
        )
    };
    if ok == 0 || output.pbData.is_null() {
        return Err("federation_dpapi_unprotect_failed".to_string());
    }
    let plaintext =
        unsafe { std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec() };
    unsafe {
        LocalFree(output.pbData as *mut core::ffi::c_void);
    }
    Ok(plaintext)
}

#[cfg(windows)]
fn open_ecdsa_provider(
) -> Result<windows_sys::Win32::Security::Cryptography::BCRYPT_ALG_HANDLE, String> {
    use windows_sys::Win32::Security::Cryptography::{
        BCryptOpenAlgorithmProvider, BCRYPT_ECDSA_P256_ALGORITHM,
    };

    let mut algorithm = std::ptr::null_mut();
    let status = unsafe {
        BCryptOpenAlgorithmProvider(
            &mut algorithm,
            BCRYPT_ECDSA_P256_ALGORITHM,
            std::ptr::null(),
            0,
        )
    };
    if status != 0 || algorithm.is_null() {
        return Err(cng_failure("federation_open_ecdsa_provider", status));
    }
    Ok(algorithm)
}

#[cfg(windows)]
fn export_key(
    key: windows_sys::Win32::Security::Cryptography::BCRYPT_KEY_HANDLE,
    blob_type: windows_sys::core::PCWSTR,
) -> Result<Vec<u8>, String> {
    use windows_sys::Win32::Foundation::STATUS_BUFFER_TOO_SMALL;
    use windows_sys::Win32::Security::Cryptography::BCryptExportKey;

    let mut size = 0u32;
    let first_status = unsafe {
        BCryptExportKey(
            key,
            std::ptr::null_mut(),
            blob_type,
            std::ptr::null_mut(),
            0,
            &mut size,
            0,
        )
    };
    if first_status != 0 && first_status != STATUS_BUFFER_TOO_SMALL {
        return Err(cng_failure("federation_export_key_size", first_status));
    }
    if size == 0 {
        return Err("federation_export_key_empty".to_string());
    }
    let mut output = vec![0u8; size as usize];
    let status = unsafe {
        BCryptExportKey(
            key,
            std::ptr::null_mut(),
            blob_type,
            output.as_mut_ptr(),
            output.len() as u32,
            &mut size,
            0,
        )
    };
    if status != 0 {
        return Err(cng_failure("federation_export_key", status));
    }
    output.truncate(size as usize);
    Ok(output)
}

#[cfg(windows)]
fn import_key(
    algorithm: windows_sys::Win32::Security::Cryptography::BCRYPT_ALG_HANDLE,
    blob: &[u8],
    blob_type: windows_sys::core::PCWSTR,
) -> Result<windows_sys::Win32::Security::Cryptography::BCRYPT_KEY_HANDLE, String> {
    use windows_sys::Win32::Security::Cryptography::BCryptImportKeyPair;

    if blob.is_empty() {
        return Err("federation_key_blob_empty".to_string());
    }
    let mut key = std::ptr::null_mut();
    let status = unsafe {
        BCryptImportKeyPair(
            algorithm,
            std::ptr::null_mut(),
            blob_type,
            &mut key,
            blob.as_ptr(),
            blob.len() as u32,
            0,
        )
    };
    if status != 0 || key.is_null() {
        return Err(cng_failure("federation_import_key", status));
    }
    Ok(key)
}

/// Generate a Windows CNG ECDSA P-256 key and protect the private blob with
/// DPAPI.  The returned private material is for local node storage only.
pub fn generate_key_material(node_id: &str) -> Result<FederationKeyMaterial, String> {
    validate_node_id(node_id)?;
    #[cfg(not(windows))]
    {
        let _ = node_id;
        return Err("federation_cng_backend_requires_windows".to_string());
    }
    #[cfg(windows)]
    {
        use windows_sys::Win32::Security::Cryptography::{
            BCryptCloseAlgorithmProvider, BCryptDestroyKey, BCryptFinalizeKeyPair,
            BCryptGenerateKeyPair, BCRYPT_ECCPRIVATE_BLOB, BCRYPT_ECCPUBLIC_BLOB,
        };

        let algorithm = open_ecdsa_provider()?;
        let mut key = std::ptr::null_mut();
        let result = (|| {
            let status = unsafe { BCryptGenerateKeyPair(algorithm, &mut key, 256, 0) };
            if status != 0 || key.is_null() {
                return Err(cng_failure("federation_generate_key_pair", status));
            }
            let status = unsafe { BCryptFinalizeKeyPair(key, 0) };
            if status != 0 {
                return Err(cng_failure("federation_finalize_key_pair", status));
            }
            let public_blob = export_key(key, BCRYPT_ECCPUBLIC_BLOB)?;
            let private_blob = export_key(key, BCRYPT_ECCPRIVATE_BLOB)?;
            let protected_private = dpapi_protect(&private_blob, &node_entropy(node_id))?;
            let public_hash = sha256_hex(&public_blob);
            Ok(FederationKeyMaterial {
                algorithm: FEDERATION_SIGNATURE_ALGORITHM.to_string(),
                public_key_hex: hex_encode(public_blob),
                public_key_sha256: public_hash.clone(),
                node_identity_hash: public_hash,
                protected_private_key_hex: hex_encode(protected_private),
                private_key_scope: "WINDOWS_DPAPI_CURRENT_USER_OR_MACHINE".to_string(),
            })
        })();
        if !key.is_null() {
            unsafe {
                BCryptDestroyKey(key);
            }
        }
        unsafe {
            BCryptCloseAlgorithmProvider(algorithm, 0);
        }
        result
    }
}

/// Sign a federation canonical body with a DPAPI-protected private blob.
pub fn sign_protected(
    node_id: &str,
    protected_private_key_hex: &str,
    message: &[u8],
) -> Result<String, String> {
    validate_node_id(node_id)?;
    #[cfg(not(windows))]
    {
        let _ = (protected_private_key_hex, message);
        return Err("federation_cng_backend_requires_windows".to_string());
    }
    #[cfg(windows)]
    {
        use windows_sys::Win32::Security::Cryptography::{
            BCryptCloseAlgorithmProvider, BCryptDestroyKey, BCryptSignHash, BCRYPT_ECCPRIVATE_BLOB,
        };

        let protected = hex_decode(protected_private_key_hex)
            .map_err(|_| "federation_protected_private_hex_invalid".to_string())?;
        let private_blob = dpapi_unprotect(&protected, &node_entropy(node_id))?;
        let algorithm = open_ecdsa_provider()?;
        let key = match import_key(algorithm, &private_blob, BCRYPT_ECCPRIVATE_BLOB) {
            Ok(key) => key,
            Err(error) => {
                unsafe { BCryptCloseAlgorithmProvider(algorithm, 0) };
                return Err(error);
            }
        };
        let digest = sha256_bytes(message);
        let mut signature = vec![0u8; FEDERATION_SIGNATURE_HEX_BYTES];
        let mut written = 0u32;
        let status = unsafe {
            BCryptSignHash(
                key,
                std::ptr::null(),
                digest.as_ptr(),
                digest.len() as u32,
                signature.as_mut_ptr(),
                signature.len() as u32,
                &mut written,
                0,
            )
        };
        unsafe {
            BCryptDestroyKey(key);
            BCryptCloseAlgorithmProvider(algorithm, 0);
        }
        if status != 0 {
            return Err(cng_failure("federation_sign_hash", status));
        }
        if written != FEDERATION_SIGNATURE_HEX_BYTES as u32 {
            return Err(format!("federation_signature_length_invalid:{written}"));
        }
        Ok(hex_encode(signature))
    }
}

/// Verify a federation canonical body with a public CNG key blob.
pub fn verify(public_key_hex: &str, message: &[u8], signature_hex: &str) -> Result<bool, String> {
    #[cfg(not(windows))]
    {
        let _ = (public_key_hex, message, signature_hex);
        return Err("federation_cng_backend_requires_windows".to_string());
    }
    #[cfg(windows)]
    {
        use windows_sys::Win32::Foundation::STATUS_INVALID_SIGNATURE;
        use windows_sys::Win32::Security::Cryptography::{
            BCryptCloseAlgorithmProvider, BCryptDestroyKey, BCryptVerifySignature,
            BCRYPT_ECCPUBLIC_BLOB,
        };

        let public_blob = hex_decode(public_key_hex)
            .map_err(|_| "federation_public_key_hex_invalid".to_string())?;
        let signature = hex_decode(signature_hex)
            .map_err(|_| "federation_signature_hex_invalid".to_string())?;
        if signature.len() != FEDERATION_SIGNATURE_HEX_BYTES {
            return Err("federation_signature_length_invalid".to_string());
        }
        let algorithm = open_ecdsa_provider()?;
        let key = match import_key(algorithm, &public_blob, BCRYPT_ECCPUBLIC_BLOB) {
            Ok(key) => key,
            Err(error) => {
                unsafe { BCryptCloseAlgorithmProvider(algorithm, 0) };
                return Err(error);
            }
        };
        let digest = sha256_bytes(message);
        let status = unsafe {
            BCryptVerifySignature(
                key,
                std::ptr::null(),
                digest.as_ptr(),
                digest.len() as u32,
                signature.as_ptr(),
                signature.len() as u32,
                0,
            )
        };
        unsafe {
            BCryptDestroyKey(key);
            BCryptCloseAlgorithmProvider(algorithm, 0);
        }
        if status == 0 {
            Ok(true)
        } else if status == STATUS_INVALID_SIGNATURE {
            Ok(false)
        } else {
            Err(cng_failure("federation_verify_signature", status))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cng_key_material_signs_and_rejects_tampering() {
        let material = generate_key_material("node-federation-rust-test")
            .expect("Windows CNG/DPAPI federation backend must be available");
        assert_eq!(material.algorithm, FEDERATION_SIGNATURE_ALGORITHM);
        assert_eq!(material.public_key_sha256, material.node_identity_hash);
        assert_eq!(material.public_key_hex.len() % 2, 0);
        let body = br#"{"federation":"offline-test","sequence":1}"#;
        let signature = sign_protected(
            "node-federation-rust-test",
            &material.protected_private_key_hex,
            body,
        )
        .expect("CNG signing should succeed");
        assert_eq!(signature.len(), FEDERATION_SIGNATURE_HEX_BYTES * 2);
        assert!(
            verify(&material.public_key_hex, body, &signature).expect("verification should run")
        );
        assert!(
            !verify(&material.public_key_hex, br#"{"sequence":2}"#, &signature)
                .expect("tampered verification should run")
        );
    }
}
