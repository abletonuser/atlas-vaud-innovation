<#
  Etape 2 : retrouve le siege (commune, NPA, localite) de chaque entreprise a partir de son numero IDE,
  dans les donnees ouvertes du registre du commerce (Zefix sur LINDAS, https://ld.admin.ch). Aucune installation.

  A lancer dans le dossier qui contient innosuisse_participants.csv :
    powershell -ExecutionPolicy Bypass -File .\ide_sieges.ps1 -Test     (verification sur 5 entreprises)
    powershell -ExecutionPolicy Bypass -File .\ide_sieges.ps1           (toutes les entreprises, quelques minutes)

  Resultat : ide_sieges.csv, a joindre dans la conversation avec innosuisse_participants.csv.
  En mode -Test, la reponse brute est enregistree dans ide_debug.json en cas de probleme.
#>
param(
  [switch]$Test,
  [string]$Fichier = "innosuisse_participants.csv",
  [int]$Batch = 150,
  [double]$Pause = 1.0,
  [string[]]$Endpoints = @("https://ld.admin.ch/query", "https://lindas.admin.ch/query")
)
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
try { [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials } catch {}

if (-not (Test-Path $Fichier)) { Write-Error "Fichier $Fichier introuvable : lancez ce script dans le dossier de la collecte."; exit 1 }
$uids = @(Import-Csv $Fichier -Encoding UTF8 | Where-Object { $_.UID -match '^CHE\d{9}$' } | ForEach-Object { $_.UID } | Sort-Object -Unique)
Write-Host "Numeros IDE distincts : $($uids.Count)"
if ($Test) { $uids = @($uids | Select-Object -First 5) }
if ($uids.Count -eq 0) { Write-Error "Aucun numero IDE dans $Fichier."; exit 1 }

function Fmt([string]$u) { return "CHE-" + $u.Substring(3, 3) + "." + $u.Substring(6, 3) + "." + $u.Substring(9, 3) }
function Invoke-Sparql([string]$q) {
  $body = "query=" + [uri]::EscapeDataString($q)
  $last = $null
  foreach ($ep in $Endpoints) {
    try {
      $r = Invoke-WebRequest -Uri $ep -Method Post -Body $body -ContentType "application/x-www-form-urlencoded; charset=utf-8" -UseBasicParsing -TimeoutSec 120 -Headers @{ Accept = "application/sparql-results+json" }
      try { $txt = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) } catch { $txt = [string]$r.Content }
      if ($Test) { Set-Content -Path "ide_debug.json" -Value $txt -Encoding UTF8 }
      return ($txt | ConvertFrom-Json)
    } catch { $last = $_.Exception.Message }
  }
  throw "Le service LINDAS ne repond pas : $last"
}
function Val($b, [string]$k) { $p = $b.PSObject.Properties[$k]; if ($p -and $p.Value) { return [string]$p.Value.value } else { return "" } }

$prefix = @"
PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
PREFIX locn: <http://www.w3.org/ns/locn#>
"@
$found = @{}
$out = New-Object System.Collections.ArrayList
for ($k = 0; $k -lt $uids.Count; $k += $Batch) {
  $chunk = @($uids[$k..([math]::Min($k + $Batch, $uids.Count) - 1)])
  $vals = ($chunk | ForEach-Object { '"' + $_ + '" "' + (Fmt $_) + '"' }) -join " "
  $q = $prefix + @"
SELECT ?uid ?name ?muni ?muniName ?zip ?town ?locality ?street WHERE {
  VALUES ?uid { $vals }
  ?id schema:value ?uid .
  ?company schema:identifier ?id .
  OPTIONAL { ?company schema:legalName ?name }
  OPTIONAL { ?company admin:municipality ?muni . OPTIONAL { ?muni schema:name ?muniName } }
  OPTIONAL { ?company schema:address ?a .
    OPTIONAL { ?a locn:postCode ?zip } OPTIONAL { ?a schema:postalCode ?zip }
    OPTIONAL { ?a locn:postName ?town } OPTIONAL { ?a schema:addressLocality ?locality }
    OPTIONAL { ?a schema:streetAddress ?street } }
}
"@
  try { $res = Invoke-Sparql $q } catch { Write-Warning $_.Exception.Message; Start-Sleep -Seconds 5; continue }
  foreach ($b in $res.results.bindings) {
    $u = (Val $b "uid") -replace '[^0-9]', ''; $u = "CHE" + $u
    if ($found.ContainsKey($u)) { continue }
    $found[$u] = 1
    $muni = Val $b "muni"
    $bfs = ([regex]::Match($muni, '(\d+)$')).Groups[1].Value
    [void]$out.Add([pscustomobject]@{ UID = $u; Name = (Val $b "name"); MunicipalityBFS = $bfs; Municipality = (Val $b "muniName")
      PostCode = (Val $b "zip"); Town = $(if (Val $b "town") { Val $b "town" } else { Val $b "locality" }); MunicipalityUri = $muni })
  }
  Write-Host ("  {0} / {1} numeros traites, {2} retrouves" -f [math]::Min($k + $Batch, $uids.Count), $uids.Count, $found.Count)
  Start-Sleep -Milliseconds ([int]($Pause * 1000))
}
if ($Test -and $found.Count -eq 0) {
  Write-Host "Aucun resultat : recherche de la structure des donnees (ide_debug_structure.json)."
  $q2 = $prefix + 'SELECT ?p ?o ?p2 ?o2 WHERE { ?c a admin:ZefixOrganisation ; ?p ?o . OPTIONAL { ?o ?p2 ?o2 } } LIMIT 80'
  try { $r2 = Invoke-Sparql $q2; $r2 | ConvertTo-Json -Depth 8 | Set-Content -Path "ide_debug_structure.json" -Encoding UTF8 } catch { Write-Warning $_.Exception.Message }
}
$out | Export-Csv -Path "ide_sieges.csv" -NoTypeInformation -Encoding UTF8
Write-Host "Termine : $($out.Count) entreprises sur $($uids.Count) retrouvees, ecrites dans ide_sieges.csv."
if ($Test) { foreach ($r in $out) { Write-Host ("  {0}  {1}  ->  {2} {3} (commune {4}, n° OFS {5})" -f $r.UID, $r.Name, $r.PostCode, $r.Town, $r.Municipality, $r.MunicipalityBFS) } }
