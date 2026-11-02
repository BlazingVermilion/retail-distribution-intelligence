# Dot-source in the current PowerShell session. Keep credentials outside the repository.
if ([string]::IsNullOrWhiteSpace($env:RDI_SF_ACCOUNT)) { throw 'Set RDI_SF_ACCOUNT to your Snowflake account identifier before running setup.' }
$env:RDI_SF_CONNECTOR_VERSION = & .\.venv-snowflake\Scripts\python.exe -c "from importlib.metadata import version; print(version('snowflake-connector-python'))"
if ($LASTEXITCODE -ne 0 -or !$env:RDI_SF_CONNECTOR_VERSION) { throw 'Cannot read the pilot connector version.' }
$env:RDI_SF_KEY_FILE = (Resolve-Path -ErrorAction Stop (Join-Path $HOME '.snowflake/rdi_pilot_key.p8')).Path
$env:RDI_SF_PASS_FILE = Join-Path $HOME '.snowflake/rdi_airflow_pass'
if (!(Test-Path -LiteralPath $env:RDI_SF_PASS_FILE)) {
    $secret = Read-Host 'Existing private key passphrase' -AsSecureString
    $buffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        # Create an empty file and restrict its ACL before writing any secret bytes.
        $f = [IO.File]::Open($env:RDI_SF_PASS_FILE, 'CreateNew', 'Write', 'None')
        $f.Dispose()
        try {
            $me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            icacls $env:RDI_SF_PASS_FILE /inheritance:r /grant:r ("*" + $me + ":F") | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Could not restrict passphrase file permissions.' }
            [IO.File]::WriteAllText($env:RDI_SF_PASS_FILE, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer), [Text.UTF8Encoding]::new($false))
        } catch { Remove-Item -LiteralPath $env:RDI_SF_PASS_FILE; throw }
    } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer); $secret.Dispose() }
}
