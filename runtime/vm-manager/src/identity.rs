use std::fs;
use std::path::Path;
use rand::Rng;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DeviceIdentity {
    pub imei: String,
    pub serialno: String,
    pub imsi: String,
    pub iccid: String,
}

impl DeviceIdentity {
    /// Calculate the Luhn check digit for a 14-digit string
    pub fn calculate_luhn(d14: &str) -> u32 {
        let mut total = 0;
        for (i, c) in d14.chars().enumerate() {
            let mut n = c.to_digit(10).unwrap_or(0);
            if i % 2 == 1 {
                n *= 2;
                if n > 9 {
                    n -= 9;
                }
            }
            total += n;
        }
        (10 - (total % 10)) % 10
    }

    /// Generate a valid 15-digit Luhn-compliant IMEI with Samsung Galaxy S24 Ultra TAC
    pub fn generate_imei() -> String {
        let mut rng = rand::thread_rng();
        // Authentic Samsung Galaxy S24 Ultra (SM-S928B) TAC
        let tac = "35847289";
        let serial: u32 = rng.gen_range(100_000..=999_999);
        let d14 = format!("{}{:06}", tac, serial);
        let check = Self::calculate_luhn(&d14);
        format!("{}{}", d14, check)
    }

    /// Generate an authentic Samsung serial number (e.g. R5CW + 7 alphanumeric chars)
    pub fn generate_serialno() -> String {
        let mut rng = rand::thread_rng();
        const CHARSET: &[u8] = b"0123456789ABCDEFGHJKLMNPQRSTUVWXYZ";
        let suffix: String = (0..7)
            .map(|_| {
                let idx = rng.gen_range(0..CHARSET.len());
                CHARSET[idx] as char
            })
            .collect();
        format!("R5CW{}", suffix)
    }

    /// Generate a 15-digit IMSI (310260 + 9 random digits)
    pub fn generate_imsi() -> String {
        let mut rng = rand::thread_rng();
        let suffix: u64 = rng.gen_range(100_000_000..=999_999_999);
        format!("310260{:09}", suffix)
    }

    /// Generate a 20-digit ICCID (898603 + 14 random digits)
    pub fn generate_iccid() -> String {
        let mut rng = rand::thread_rng();
        let part1: u64 = rng.gen_range(10_000_000..=99_999_999);
        let part2: u64 = rng.gen_range(100_000..=999_999);
        format!("898603{}{}", part1, part2)
    }

    /// Generate a completely new device identity
    pub fn new_random() -> Self {
        Self {
            imei: Self::generate_imei(),
            serialno: Self::generate_serialno(),
            imsi: Self::generate_imsi(),
            iccid: Self::generate_iccid(),
        }
    }

    /// Load identity from AVD directory, or generate a fresh one and save it
    pub fn load_or_generate(avd_dir: &Path) -> Self {
        let ini_path = avd_dir.join("device_identity.ini");
        if let Ok(content) = fs::read_to_string(&ini_path) {
            let mut imei = String::new();
            let mut serialno = String::new();
            let mut imsi = String::new();
            let mut iccid = String::new();

            for line in content.lines() {
                let line = line.trim();
                if let Some((k, v)) = line.split_once('=') {
                    match k.trim() {
                        "imei" => imei = v.trim().to_string(),
                        "serialno" => serialno = v.trim().to_string(),
                        "imsi" => imsi = v.trim().to_string(),
                        "iccid" => iccid = v.trim().to_string(),
                        _ => {}
                    }
                }
            }

            if !imei.is_empty() && !serialno.is_empty() {
                return Self {
                    imei,
                    serialno,
                    imsi: if imsi.is_empty() { Self::generate_imsi() } else { imsi },
                    iccid: if iccid.is_empty() { Self::generate_iccid() } else { iccid },
                };
            }
        }

        // Also check if imei.txt exists
        let imei_txt = avd_dir.join("imei.txt");
        let existing_imei = if let Ok(s) = fs::read_to_string(&imei_txt) {
            let s = s.trim().to_string();
            if s.len() == 15 { Some(s) } else { None }
        } else {
            None
        };

        let identity = Self {
            imei: existing_imei.unwrap_or_else(Self::generate_imei),
            serialno: Self::generate_serialno(),
            imsi: Self::generate_imsi(),
            iccid: Self::generate_iccid(),
        };

        let _ = identity.save_to_avd(avd_dir);
        identity
    }

    /// Save identity files to AVD directory
    pub fn save_to_avd(&self, avd_dir: &Path) -> std::io::Result<()> {
        let _ = fs::create_dir_all(avd_dir);

        // 1. Write imei.txt
        let imei_path = avd_dir.join("imei.txt");
        fs::write(&imei_path, format!("{}\n", self.imei))?;

        // 2. Write device_identity.ini
        let ini_path = avd_dir.join("device_identity.ini");
        let ini_content = format!(
            "[identity]\nimei={}\nserialno={}\nimsi={}\niccid={}\n",
            self.imei, self.serialno, self.imsi, self.iccid
        );
        fs::write(&ini_path, ini_content)?;

        // 3. Write or update iccprofile_for_sim0.xml
        let modem_dir = avd_dir.join("modem_simulator");
        let _ = fs::create_dir_all(&modem_dir);
        let sim_xml_path = modem_dir.join("iccprofile_for_sim0.xml");
        self.provision_sim_xml(&sim_xml_path)?;

        Ok(())
    }

    fn provision_sim_xml(&self, target_path: &Path) -> std::io::Result<()> {
        if target_path.exists() {
            if let Ok(xml) = fs::read_to_string(target_path) {
                let mut new_xml = xml;
                if let Some(start) = new_xml.find("<CCID>") {
                    if let Some(end) = new_xml[start..].find("</CCID>") {
                        new_xml.replace_range(start + 6..start + end, &self.iccid);
                    }
                }
                if let Some(start) = new_xml.find("<CIMI>") {
                    if let Some(end) = new_xml[start..].find("</CIMI>") {
                        new_xml.replace_range(start + 6..start + end, &self.imsi);
                    }
                }
                return fs::write(target_path, new_xml);
            }
        }

        // Minimal default SIM profile if none exists
        let default_sim = format!(
            r#"<IccProfile>
    <MF path="3F00">
        <EF name="EF_ICCID" id="2FE2" structure="transparent">
            <CCID>{}</CCID>
        </EF>
        <ADF name="USIM" path="7FFF" aid="A0000000871002FF86FF0389FFFFFFFF">
            <EF name="EF_IMSI" id="6F07" structure="transparent">
                <CIMI>{}</CIMI>
            </EF>
        </ADF>
    </MF>
</IccProfile>
"#,
            self.iccid, self.imsi
        );
        fs::write(target_path, default_sim)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_luhn_algorithm() {
        // Test known valid IMEIs
        assert_eq!(DeviceIdentity::calculate_luhn("86740002204719"), 9);
        assert_eq!(DeviceIdentity::calculate_luhn("35847289000001"), 0);

        // Test generated IMEI
        let imei = DeviceIdentity::generate_imei();
        assert_eq!(imei.len(), 15);
        assert!(imei.starts_with("35847289"));
        let (d14, check_char) = imei.split_at(14);
        let expected_check = DeviceIdentity::calculate_luhn(d14);
        assert_eq!(check_char.parse::<u32>().unwrap(), expected_check);
    }

    #[test]
    fn test_device_identity_generation() {
        let id1 = DeviceIdentity::new_random();
        let id2 = DeviceIdentity::new_random();

        assert_ne!(id1.imei, id2.imei);
        assert_ne!(id1.serialno, id2.serialno);
        assert!(id1.serialno.starts_with("R5CW"));
        assert_eq!(id1.serialno.len(), 11);
        assert_eq!(id1.imsi.len(), 15);
        assert_eq!(id1.iccid.len(), 20);
    }
}
