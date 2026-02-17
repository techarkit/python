import argparse
import logging
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Any, Tuple

import paramiko
import yaml

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("health_check_debug.log"), logging.StreamHandler(sys.stdout)],
)

# ----------------------------
# Vault helpers
# ----------------------------
def _decrypt_with_ansible_api(vault_file_path: str, vault_password: str) -> str:
    """
    Decrypt an Ansible Vault file using ansible python API (preferred).
    Requires: ansible-core installed (python import 'ansible').
    """
    from ansible.parsing.vault import VaultLib, VaultSecret
    from ansible.constants import DEFAULT_VAULT_ID_MATCH

    with open(vault_file_path, "rb") as f:
        ciphertext = f.read()

    vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(vault_password.encode("utf-8")))])
    plaintext = vault.decrypt(ciphertext)
    return plaintext.decode("utf-8")


def _decrypt_with_ansible_cli(vault_file_path: str, vault_password_file: Optional[str]) -> str:
    """
    Fallback decryption using ansible-vault CLI.
    Requires: ansible-vault available in PATH.
    """
    import subprocess

    cmd = ["ansible-vault", "view", vault_file_path]
    if vault_password_file:
        cmd += ["--vault-password-file", vault_password_file]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ansible-vault view failed: {proc.stderr.strip()}")
    return proc.stdout


def load_vault_config(
    vault_file_path: str,
    vault_password_file: Optional[str],
    vault_password_env: Optional[str],
) -> Dict[str, Any]:
    """
    Loads YAML from an Ansible Vault encrypted file.
    Uses ansible python API if available, otherwise falls back to ansible-vault CLI.
    """
    start_time = time.time()
    logging.debug("Loading vault config: %s", vault_file_path)

    vault_password = None
    if vault_password_env:
        vault_password = os.environ.get(vault_password_env)
        if not vault_password:
            raise ValueError(f"Environment variable '{vault_password_env}' is not set or empty.")

    # Try ansible python API first (if we have password text)
    if vault_password:
        try:
            plaintext = _decrypt_with_ansible_api(vault_file_path, vault_password)
            config = yaml.safe_load(plaintext)
            logging.debug("Config decrypted via ansible API in %.2f seconds", time.time() - start_time)
            return config
        except Exception as e:
            logging.warning("Ansible API decrypt failed, will try CLI fallback: %s", str(e))

    # CLI fallback needs either --vault-password-file OR interactive prompt
    plaintext = _decrypt_with_ansible_cli(vault_file_path, vault_password_file)
    config = yaml.safe_load(plaintext)
    logging.debug("Config decrypted via ansible-vault CLI in %.2f seconds", time.time() - start_time)
    return config


# ----------------------------
# NetApp output parsing
# ----------------------------
def parse_lun_output(output: str) -> Tuple[str, bool]:
    if not output.strip() or "There are no entries matching your query" in output:
        return "None", False
    lines = output.splitlines()
    data_lines = [line.strip() for line in lines if line.strip()]
    return "\n".join(data_lines), True


def parse_volume_output(output: str) -> Tuple[str, bool]:
    if not output.strip() or "There are no entries matching your query" in output:
        return "None", False
    lines = output.splitlines()
    data_lines = [line.strip() for line in lines if line.strip()]
    return "\n".join(data_lines[2:]), True if len(data_lines) > 2 else False


# ----------------------------
# SSH / Commands
# ----------------------------
def run_commands(host: str, username: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    results: Dict[str, Any] = {}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=username, password=password, timeout=10)

        commands = [
            "system health alert show",
            "vol show -state offline",
            "lun show -state offline",
            "df -i -percent-inodes-used >90",
            "disk show -broken",
            "net int show -is-home false",
            "event log show -severity EMERGENCY -time >2d -event !secd.ldap.noServers*,!secd.lsa.noServers*,!secd.netlogon.noServers*",
            "storage failover show",
            "storage shelf show -errors",
            "job show -state failure",
        ]

        for cmd in commands:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            output = stdout.read().decode(errors="ignore").strip()

            if cmd == "system health alert show":
                results[cmd] = {"message": "None" if "empty" in output else output, "show_cmd": "empty" not in output}

            elif cmd == "vol show -state offline":
                msg, show = parse_volume_output(output)
                results[cmd] = {"message": msg, "show_cmd": show}

            elif cmd == "lun show -state offline":
                msg, show = parse_lun_output(output)
                results[cmd] = {"message": msg, "show_cmd": show}

            elif cmd in ["disk show -broken", "df -i -percent-inodes-used >90", "storage shelf show -errors", "job show -state failure"]:
                results[cmd] = {"message": "None" if "no entries" in output.lower() else output, "show_cmd": "no entries" not in output.lower()}

            elif cmd == "net int show -is-home false":
                results[cmd] = {"message": "All at home" if "no entries" in output.lower() else output, "show_cmd": "no entries" not in output.lower()}

            elif cmd.startswith("event log show"):
                results[cmd] = {"message": "None" if "no entries" in output.lower() else output, "show_cmd": "no entries" not in output.lower()}

            elif cmd == "storage failover show":
                logging.debug("Raw storage failover show output:\n%s", output)

                lines = output.splitlines()
                skip_keywords = ["Last login", "Takeover", "Node", "----", "entries were displayed", ""]
                cleaned_lines = []
                for line in lines:
                    line = line.strip()
                    if not line or any(skip in line for skip in skip_keywords):
                        continue
                    cleaned_lines.append(line)

                # merge potentially split lines
                data_lines = []
                i = 0
                while i < len(cleaned_lines):
                    current_line = cleaned_lines[i]
                    if "true" not in current_line.lower() and "connected" not in current_line.lower() and i + 1 < len(cleaned_lines):
                        data_lines.append(current_line + " " + cleaned_lines[i + 1])
                        i += 2
                    else:
                        data_lines.append(current_line)
                        i += 1

                node_status_lines = []
                for line in data_lines:
                    if re.search(r"\b(true|false)\b", line, re.IGNORECASE):
                        node_status_lines.append(line)

                if not node_status_lines:
                    results[cmd] = {"message": "Healthy", "show_cmd": False}
                    continue

                is_healthy = True
                for line in node_status_lines:
                    ll = line.lower()
                    if not ("true" in ll and "connected" in ll):
                        is_healthy = False

                if is_healthy:
                    results[cmd] = {"message": "Healthy", "show_cmd": False}
                else:
                    results[cmd] = {"message": "<br>".join(node_status_lines), "show_cmd": True}

        client.close()
        return results, None

    except Exception as e:
        return None, str(e)


# ----------------------------
# HTML report
# ----------------------------
def build_html_report(data: Dict[str, Any], title_suffix: str = "") -> str:
    html = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
        body { font-family: 'Roboto', sans-serif; margin: 20px; color: #333; background-color: #fff; }
        table { border-collapse: collapse; width: 100%; font-size: 13px; }
        th, td { border: 1px solid #ccc; padding: 6px 10px; vertical-align: top; }
        th { background-color: #0074d9; color: white; text-align: left; }
        td span.issue { color: #d9534f; font-weight: bold; white-space: pre-line; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        tr:hover { background-color: #eef; }
    </style>
    """

    today = datetime.now().strftime("%Y-%m-%d")
    heading = f"NetApp Health Checks - {today}"
    if title_suffix:
        heading += f" - {title_suffix}"
    html += f"<h2>{heading}</h2>"

    all_commands = set()
    for cluster_data in data.values():
        if "results" in cluster_data and cluster_data["results"]:
            all_commands.update(cluster_data["results"].keys())
    all_commands = sorted(list(all_commands))

    cmd_aliases = {
        "df -i -percent-inodes-used >90": "Inode Issues",
        "disk show -broken": "Broken Disks",
        "event log show -severity EMERGENCY -time >2d -event !secd.ldap.noServers*,!secd.lsa.noServers*,!secd.netlogon.noServers*": "Emergency Events",
        "job show -state failure": "Failed Jobs",
        "lun show -state offline": "Offline LUNs",
        "net int show -is-home false": "LIFs Not at Home",
        "storage failover show": "Storage Failover Health",
        "storage shelf show -errors": "Shelf Errors",
        "system health alert show": "Health Alerts",
        "vol show -state offline": "Offline Volumes",
    }

    html += "<table>"
    html += "<tr><th>Cluster</th>" + "".join(f"<th>{cmd_aliases.get(cmd, cmd)}</th>" for cmd in all_commands) + "</tr>"

    for cluster, info in data.items():
        html += f"<tr><td><b>{cluster}</b></td>"
        if "error" in info:
            html += f"<td colspan='{len(all_commands)}'><span class='issue'>{info['error']}</span></td>"
        else:
            results = info.get("results", {}) or {}
            for cmd in all_commands:
                if cmd in results:
                    msg = results[cmd]["message"]
                    cell = f"<span class='issue'>{msg.replace(chr(10), '<br>')}</span>" if results[cmd]["show_cmd"] else msg
                else:
                    cell = "N/A"
                html += f"<td>{cell}</td>"
        html += "</tr>"

    html += "</table>"
    return html


# ----------------------------
# Email send
# ----------------------------
def send_email(
    smtp_server: str,
    smtp_port: int,
    sender: str,
    to_list: List[str],
    cc_list: List[str],
    subject: str,
    html_body: str,
) -> None:
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to_list) if to_list else ""
    msg["Cc"] = ", ".join(cc_list) if cc_list else ""
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    recipients = (to_list or []) + (cc_list or [])
    if not recipients:
        raise ValueError("No recipients resolved (both To and Cc are empty).")

    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
        server.sendmail(sender, recipients, msg.as_string())
        logging.info("Email sent to=%s cc=%s subject=%s", to_list, cc_list, subject)


def _ensure_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    return [str(val)]


def resolve_recipients(cluster_cfg: Dict[str, Any], defaults_cfg: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    to_list = _ensure_list(cluster_cfg.get("to")) or _ensure_list(defaults_cfg.get("to"))
    cc_list = _ensure_list(cluster_cfg.get("cc")) or _ensure_list(defaults_cfg.get("cc"))
    return to_list, cc_list


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="NetApp health checks with Ansible Vault config + per-cluster email routing.")
    parser.add_argument("--config", default="config.yaml", help="Path to Ansible Vault-encrypted YAML config (default: config.yaml)")
    parser.add_argument("--vault-password-file", default=None, help="Path to vault password file (recommended for automation)")
    parser.add_argument("--vault-password-env", default=None, help="Env var name that contains vault password (e.g. ANSIBLE_VAULT_PASSWORD)")
    parser.add_argument("--cluster", action="append", help="Run only for a specific cluster name (can be used multiple times)")
    parser.add_argument("--per-cluster-email", action="store_true", help="Send one email per cluster (recommended if To/CC differ)")
    parser.add_argument("--combined-email", action="store_true", help="Send one combined email to defaults.to/defaults.cc")
    args = parser.parse_args()

    if args.per_cluster_email and args.combined_email:
        raise ValueError("Choose either --per-cluster-email OR --combined-email, not both.")

    config = load_vault_config(args.config, args.vault_password_file, args.vault_password_env)

    smtp_cfg = config.get("smtp", {}) or {}
    defaults_cfg = config.get("defaults", {}) or {}
    clusters = config.get("clusters", []) or []

    smtp_server = smtp_cfg.get("server", "localhost")
    smtp_port = int(smtp_cfg.get("port", 25))
    sender = smtp_cfg.get("sender")
    if not sender:
        raise ValueError("smtp.sender is required in config.")

    subject_prefix = smtp_cfg.get("subject_prefix", "NetApp Health Checks")

    selected_names = set(args.cluster or [])
    filtered = []
    for c in clusters:
        if c.get("enabled", True) is False:
            continue
        if selected_names and c.get("name") not in selected_names:
            continue
        filtered.append(c)

    if not filtered:
        raise ValueError("No clusters selected (check --cluster filter / enabled flags).")

    all_results: Dict[str, Any] = {}
    for cluster in filtered:
        name = cluster["name"]
        ip = cluster["ip"]
        username = cluster["username"]
        password = cluster["password"]

        logging.info("Checking cluster: %s (%s)", name, ip)
        results, error = run_commands(ip, username, password)
        all_results[name] = {"results": results} if results else {"error": error}

    if args.combined_email:
        html_report = build_html_report(all_results, title_suffix="(Combined)")
        to_list = _ensure_list(defaults_cfg.get("to"))
        cc_list = _ensure_list(defaults_cfg.get("cc"))
        subject = f"{subject_prefix} - Combined - {datetime.now().strftime('%Y-%m-%d')}"
        send_email(smtp_server, smtp_port, sender, to_list, cc_list, subject, html_report)
        print("Combined health check email sent.")
        return

    # default to per-cluster email behavior
    for cluster in filtered:
        name = cluster["name"]
        per_cluster_data = {name: all_results[name]}
        html_report = build_html_report(per_cluster_data, title_suffix=name)

        to_list, cc_list = resolve_recipients(cluster, defaults_cfg)
        subject = f"{subject_prefix} - {name} - {datetime.now().strftime('%Y-%m-%d')}"
        send_email(smtp_server, smtp_port, sender, to_list, cc_list, subject, html_report)

    print("Per-cluster health check email(s) sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error("Script failed: %s", str(e))
        sys.exit(1)
