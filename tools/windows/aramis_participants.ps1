<#
  Collecte les participants (organisation, NPA, localite) des projets Innosuisse publies dans ARAMIS.
  Version PowerShell : aucune installation necessaire sous Windows.

  Utilisation, dans le dossier du fichier :
    powershell -ExecutionPolicy Bypass -File .\aramis_participants.ps1 -Test     (verification, environ une minute)
    powershell -ExecutionPolicy Bypass -File .\aramis_participants.ps1           (collecte complete, environ 2 a 3 heures)

  Etape 1 : liste des projets, lue sur les pages publiques https://datenausgabe.aramis.admin.ch/projects
  Etape 2 : participants de chaque projet, par le service web ARAMIS ou, a defaut, la page publique "Beteiligte".
  La collecte peut etre interrompue (Ctrl+C) puis relancee : chaque projet lu est garde dans le dossier aramis_cache_v4.
  Aucun nom de personne, e-mail ou telephone n'est conserve. Resultat : innosuisse_participants.csv.
  En cas de probleme, le mode -Test enregistre les pages recues (aramis_debug_*.html) : joignez-les a la conversation.
#>
param(
  [switch]$Test,
  [int]$Depuis = 2018,
  [double]$Pause = 0.6,
  [int]$Max = 0,
  [string]$ListUrl = "https://datenausgabe.aramis.admin.ch/projects",
  [string]$PageUrl = "https://www.aramis.admin.ch/Beteiligte/?ProjectID={0}&Sprache=de-CH",
  [string[]]$WsUrls = @("https://www.webservice.aramis.admin.ch/public/service.svc/project/?aramisId={0}&Language=FR",
                        "https://www.webservice.aramis.admin.ch/Public/Service.svc/project/?aramisId={0}&Language=FR")
)
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
try { [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials } catch {}
$InnoNum = '\s(IP|INNO|INT)-[A-Z]+\s*$'

function Get-Text([string]$Uri, [string]$Accept = "text/html") {
  $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60 -Headers @{ Accept = $Accept; "User-Agent" = "carte-innovation-vaud/1.1 (collecte ponctuelle, cadence lente)" }
  try { $bytes = $r.RawContentStream.ToArray(); return [System.Text.Encoding]::UTF8.GetString($bytes).Trim([char]0xFEFF) } catch { return [string]$r.Content }
}
function Strip([string]$h) {
  $t = [regex]::Replace($h, '<[^>]+>', ' ')
  $t = [System.Net.WebUtility]::HtmlDecode($t)
  return ([regex]::Replace($t, '\s+', ' ')).Trim()
}
function Pause-Short { Start-Sleep -Milliseconds ([int]($Pause * 1000)) }

# ---------- 1. Liste des projets ----------
function Parse-ListPage([string]$html) {
  $rows = @()
  foreach ($m in [regex]::Matches($html, '(?is)<tr\b.*?</tr>')) {
    $tr = $m.Value
    $id = [regex]::Match($tr, 'ProjectID=(\d+)')
    if (-not $id.Success) { continue }
    $cells = @([regex]::Matches($tr, '(?is)<td\b[^>]*>(.*?)</td>') | ForEach-Object { Strip $_.Groups[1].Value })
    $num = ($cells | Where-Object { $_ -match $InnoNum } | Select-Object -First 1)
    if (-not $num -and $cells.Count -gt 0) { $num = $cells[0] }
    $txt = Strip $tr
    $dates = @([regex]::Matches($txt, '\b(\d{2})\.(\d{2})\.(\d{4})\b') | ForEach-Object { [int]$_.Groups[3].Value })
    $year = if ($dates.Count -gt 0) { $dates[0] } else { $null }
    $rows += [pscustomobject]@{ Id = $id.Groups[1].Value; ProjectNumber = $num; Office = $txt; Year = $year }
  }
  return $rows
}
$listCache = "aramis_projets_v4.csv"
if (-not $Test -and (Test-Path $listCache)) {
  $projects = @(Import-Csv $listCache -Encoding UTF8)
  Write-Host "Etape 1 : liste des projets reprise de $listCache ($($projects.Count) projets)"
} else {
Write-Host "Etape 1 : liste des projets ARAMIS"
$first = Get-Text $ListUrl
if ($Test) { Set-Content -Path "aramis_debug_list.html" -Value $first -Encoding UTF8 }
$filter = ""
foreach ($sel in [regex]::Matches($first, '(?is)<select\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</select>')) {
  foreach ($op in [regex]::Matches($sel.Groups[2].Value, '(?is)<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>')) {
    $label = Strip $op.Groups[2].Value
    if ($label -match 'INNOSUISSE' -and $label -notmatch 'EVAL' -and $op.Groups[1].Value) {
      $filter = "&" + [uri]::EscapeDataString($sel.Groups[1].Value) + "=" + [uri]::EscapeDataString([System.Net.WebUtility]::HtmlDecode($op.Groups[1].Value))
    }
  }
}
$sortQ = "q%5Bs%5D=start_date+desc"
function ListUri([int]$page, [string]$f) { return "{0}?{1}{2}&page={3}" -f $ListUrl, $sortQ, $f, $page }
$p1 = Get-Text (ListUri 1 $filter); $rows1 = @(Parse-ListPage $p1)
if ($filter) {
  $share = if ($rows1.Count) { @($rows1 | Where-Object { $_.Office -match 'INNOSUISSE' }).Count / $rows1.Count } else { 0 }
  if ($share -lt 0.8) { Write-Host "  filtre Innosuisse ignore (non applique par le site)"; $filter = ""; $p1 = Get-Text (ListUri 1 ""); $rows1 = @(Parse-ListPage $p1) }
  else { Write-Host "  filtre Innosuisse actif" }
}
$lastPage = (@(@([regex]::Matches($p1, 'page=(\d+)') | ForEach-Object { [int]$_.Groups[1].Value }) + 1) | Measure-Object -Maximum).Maximum
$yrs = @($rows1 | Where-Object { $_.Year } | ForEach-Object { $_.Year })
$sorted = $yrs.Count -ge 2 -and $yrs[0] -ge $yrs[-1]
Write-Host ("  page 1 : {0} projets lus ; {1} pages au total ; tri par date {2}" -f $rows1.Count, $lastPage, $(if ($sorted) { "actif" } else { "non confirme, lecture de toutes les pages" }))
if ($rows1.Count -eq 0) { Write-Error "Aucun projet reconnu sur la page de liste. Joignez le fichier aramis_debug_list.html a la conversation (relancer avec -Test)."; exit 1 }
$projects = New-Object System.Collections.ArrayList
$seen = @{}
$page = 1; $rows = $rows1
while ($true) {
  foreach ($r in $rows) {
    $isInno = ($r.ProjectNumber -match $InnoNum) -or ($r.Office -match 'INNOSUISSE' -and $r.Office -notmatch 'EVAL')
    if ($isInno -and ($null -eq $r.Year -or $r.Year -ge $Depuis) -and -not $seen.ContainsKey($r.Id)) { $seen[$r.Id] = 1; [void]$projects.Add($r) }
  }
  $pageYears = @($rows | Where-Object { $_.Year } | ForEach-Object { $_.Year })
  if ($Test -or $page -ge $lastPage -or ($Max -gt 0 -and $projects.Count -ge $Max)) { break }
  if ($sorted -and $pageYears.Count -gt 0 -and ($pageYears | Measure-Object -Maximum).Maximum -lt $Depuis) { break }
  $page++; Pause-Short
  try { $rows = @(Parse-ListPage (Get-Text (ListUri $page $filter))) } catch { Write-Warning "  page $page : echec ($($_.Exception.Message)), on continue"; $rows = @() }
  if ($page % 25 -eq 0) { Write-Host "  page $page / $lastPage : $($projects.Count) projets Innosuisse retenus" }
}
if (-not $Test -and $Max -eq 0) { $projects | Select-Object Id, ProjectNumber, Year | Export-Csv -Path $listCache -NoTypeInformation -Encoding UTF8 }
}
if ($Test) { $projects = @($projects | Select-Object -First 3) } elseif ($Max -gt 0) { $projects = @($projects | Select-Object -First $Max) }
Write-Host "Projets Innosuisse a lire : $($projects.Count)"

# ---------- 2. Participants ----------
$Title = '^(?:(?:Prof(?:essor|esseur)?|Dr|Doktor|Docteur|PD|Herr|Frau|Monsieur|Madame|Mme|Dipl\.?\s?Ing)\.?\s*)+$'
$OrgKw = '(?i)\b(SA|AG|GmbH|S[aà]rl|Sagl|Ltd|Inc|SE|KG|Genossenschaft|Coop[ée]rative|Stiftung|Fondation|Foundation|Verein|Association|Universit\w*|Hochschule|Fachhochschule|Haute|[EÉ]cole|School|Institut\w*|Center|Centre|Zentrum|EPFL|ETH|ETHZ|HES|HES-SO|HEIG-VD|ZHAW|FHNW|BFH|HSLU|OST|SUPSI|EMPA|Eawag|PSI|WSL|CSEM|Idiap|Spital|H[ôo]pital|Clinique|Klinik|CHUV|Group|Holding|Labs?)\b'
$Street = '(?i)(\d|strasse|str\.|weg|gasse|rue|avenue|av\.|chemin|ch\.|route|rte|via|platz|place|quai|boulevard|bd|all[ée]e|station|postfach|case postale|parc|campus)'
function Parse-Person([string[]]$lines, [string]$role) {
  $L = @($lines | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch '@' -and $_ -notmatch '^(\+|0)\d[\d\s/().-]{6,}' -and $_ -notmatch '^(https?://|www\.)' -and $_ -notmatch '^CHE\d{9}$' -and $_ -notmatch $Title })
  $npa = ""; $city = ""; $country = ""; $iz = -1
  for ($k = 0; $k -lt $L.Count; $k++) {
    $m = [regex]::Match($L[$k], '^([A-Z]{1,3})-\s?(\d{4,5})\s+(.+)$')
    if ($m.Success) { $country = $m.Groups[1].Value; $npa = $m.Groups[2].Value; $city = $m.Groups[3].Value; $iz = $k }
  }
  if ($iz -eq 0) { $before = @() } elseif ($iz -gt 0) { $before = @($L[0..($iz - 1)]) } else { $before = $L }
  # la ligne juste avant le NPA est la rue
  if ($iz -gt 0 -and $before.Count -ge 1 -and $before[-1] -match $Street -and $before[-1] -notmatch $OrgKw) {
    if ($before.Count -ge 2) { $before = @($before[0..($before.Count - 2)]) } else { $before = @() }
  }
  # la premiere ligne restante est le nom de la personne quand elle ne ressemble pas a une organisation
  if ($before.Count -ge 2 -and $before[0] -notmatch $OrgKw) { $before = @($before[1..($before.Count - 1)]) }
  $company = ""
  foreach ($b in $before) { if ($company -and $b -cmatch '^[a-zàâçéèêëîïôûù]') { $company += $b } else { $company = ($company + " " + $b).Trim() } }
  if ($company -and $company -notmatch $OrgKw -and $company -cmatch "^[A-ZÀ-Ý][\w'-]+(\s[A-ZÀ-Ý][\w'-]+){1,2}$") { $company = "" }   # ressemble a un nom de personne
  $uidm = [regex]::Match(($lines -join " "), 'CHE-?(\d{3})\.?(\d{3})\.?(\d{3})')
  $uid = if ($uidm.Success) { "CHE" + $uidm.Groups[1].Value + $uidm.Groups[2].Value + $uidm.Groups[3].Value } else { "" }
  return [pscustomobject]@{ UID = $uid; KindOfParticipation = $role; Type = ""; Company = $company; PostCode = $npa; City = $city; Canton = ""; Country = $country }
}
function Get-FromPage([string]$id) {
  $html = Get-Text ($PageUrl -f $id)
  if ($Test) { Set-Content -Path "aramis_debug_project_$id.html" -Value $html -Encoding UTF8 }
  $out = @()
  foreach ($tr in [regex]::Matches($html, '(?is)<tr\b.*?</tr>')) {
    $cells = @([regex]::Matches($tr.Value, '(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>') | ForEach-Object { $_.Groups[1].Value })
    if ($cells.Count -lt 2) { continue }
    $role = Strip $cells[0]
    if (-not $role -or $role.Length -gt 40 -or $role -match 'Bundesstelle|Verwaltungseinheit|Office f[ée]d[ée]ral') { continue }
    $raw = [regex]::Replace($cells[1], '(?i)<br\s*/?>|</p>|</div>|</li>|</span>', "`n")
    $raw = [regex]::Replace($raw, '(?i)<a\b[^>]*href="[^"]*?(CHE\d{9})[^"]*"[^>]*>.*?</a>', "`n`$1`n")
    $lines = @(([System.Net.WebUtility]::HtmlDecode([regex]::Replace($raw, '<[^>]+>', ''))) -split "`n" | ForEach-Object { ($_ -replace '\s+', ' ').Trim() } | Where-Object { $_ })
    if ($lines.Count -eq 0) { continue }
    $out += Parse-Person $lines $role
  }
  return $out
}
function Join-Parts($vals) {
  # Les champs ARAMIS sont coupes a 35 caracteres : on recolle sans espace quand la suite commence par une minuscule.
  $r = ""
  foreach ($x in $vals) { if (-not $x) { continue }; $x = ($x -replace '\s+', ' ').Trim(); if ($r -and $x -cmatch '^[a-zàâçéèêëîïôûù]') { $r += $x } else { $r = ($r + " " + $x).Trim() } }
  return $r
}
function Flat-Json($o, $acc) {
  # Aplati un objet JSON : champs simples, et textes localises {LanguageCode, Text} ramenes a leur texte (FR de preference).
  if ($null -eq $o -or $o -is [string] -or $o.GetType().IsPrimitive) { return }
  if ($o -is [array]) { foreach ($x in $o) { Flat-Json $x $acc }; return }
  foreach ($pp in $o.PSObject.Properties) {
    $v = $pp.Value
    if ($null -eq $v) { continue }
    if ($v -is [string] -or $v.GetType().IsPrimitive) { if (-not $acc[$pp.Name]) { $acc[$pp.Name] = [string]$v }; continue }
    $names = @($v.PSObject.Properties.Name)
    if ($names -contains "Text" -and $names -contains "LanguageCode") { if (-not $acc[$pp.Name]) { $acc[$pp.Name] = [string]$v.Text }; continue }
    if ($v -is [array] -and $v.Count -gt 0 -and $null -ne $v[0] -and @($v[0].PSObject.Properties.Name) -contains "LanguageCode") {
      $fr = @($v | Where-Object { $_.LanguageCode -eq "FR" }) + @($v) | Select-Object -First 1
      if (-not $acc[$pp.Name]) { $acc[$pp.Name] = [string]$fr.Text }; continue
    }
    Flat-Json $v $acc
  }
}
function Flat-Xml($node, $acc) {
  foreach ($c in $node.ChildNodes) {
    if ($c.NodeType -ne [System.Xml.XmlNodeType]::Element) { continue }
    $kids = @($c.ChildNodes | Where-Object { $_.NodeType -eq [System.Xml.XmlNodeType]::Element })
    $kn = @($kids | ForEach-Object { $_.LocalName })
    if ($kids.Count -eq 0) { if (-not $acc[$c.LocalName]) { $acc[$c.LocalName] = $c.InnerText } }
    elseif ($kn -contains "Text" -and $kn -contains "LanguageCode") { if (-not $acc[$c.LocalName]) { $acc[$c.LocalName] = ($kids | Where-Object { $_.LocalName -eq "Text" } | Select-Object -First 1).InnerText } }
    elseif ($kids[0].LocalName -match 'LocalizedText') { $t = $kids | ForEach-Object { $_ } | Where-Object { $_.SelectSingleNode("*[local-name()='LanguageCode']").InnerText -eq "FR" } | Select-Object -First 1; if (-not $t) { $t = $kids[0] }; if (-not $acc[$c.LocalName]) { $acc[$c.LocalName] = $t.SelectSingleNode("*[local-name()='Text']").InnerText } }
    else { Flat-Xml $c $acc }
  }
}
function First-Of($acc, [string[]]$keys) { foreach ($k in $keys) { if ($acc[$k]) { return [string]$acc[$k] } }; return "" }
function To-Part($acc) {
  $uidm = [regex]::Match(((@($acc["URL1"], $acc["URL2"], $acc["ShortDesignation"]) | Where-Object { $_ }) -join " "), 'CHE-?(\d{3})\.?(\d{3})\.?(\d{3})')
  return [pscustomobject]@{
    UID = $(if ($uidm.Success) { "CHE" + $uidm.Groups[1].Value + $uidm.Groups[2].Value + $uidm.Groups[3].Value } else { "" })
    KindOfParticipation = (First-Of $acc @("KindOfParticipation", "ParticipationKind", "Role"))
    Type = (First-Of $acc @("Type", "ParticipantType"))
    Company = (Join-Parts @($acc["Company1"], $acc["Company2"], $acc["Company3"], $acc["Company4"]))
    PostCode = (First-Of $acc @("PostCode", "PostalCode", "ZipCode", "Zip", "Plz", "PLZ", "NPA"))
    City = (First-Of $acc @("City", "Town", "Place", "Ort", "Locality"))
    Canton = (First-Of $acc @("Canton", "CantonCode", "Kanton", "Region"))
    Country = (First-Of $acc @("Country", "CountryCode", "Land"))
  }
}
function Get-FromWs([string]$id) {
  foreach ($u in $WsUrls) {
    try {
      $txt = Get-Text ($u -f $id) "application/json"
      if ($Test) { Set-Content -Path "aramis_debug_ws_$id.txt" -Value $txt -Encoding UTF8 }
      $parts = @()
      if ($txt.StartsWith("{")) {
        $o = $txt | ConvertFrom-Json; if ($o.PSObject.Properties.Name -contains "d") { $o = $o.d }
        foreach ($q in @($o.Participants)) { if ($null -eq $q) { continue }; $acc = @{}; Flat-Json $q $acc; $parts += To-Part $acc }
      } else {
        $x = [xml]$txt
        foreach ($q in $x.SelectNodes("//*[local-name()='Participant']")) { $acc = @{}; Flat-Xml $q $acc; $parts += To-Part $acc }
      }
      if ($parts.Count -gt 0) { return ,$parts }
    } catch { }
  }
  return $null
}
function Norm([string]$s) { return ([regex]::Replace($s.ToLowerInvariant(), '[^a-z0-9]', '')) }
function Add-Addresses($parts, [string]$id) {
  # Le service web ne publie pas toujours l'adresse : on la reprend de la page publique "Beteiligte".
  if (@($parts | Where-Object { -not $_.PostCode }).Count -eq 0) { return $parts }
  try { $page = @(Get-FromPage $id) } catch { return $parts }
  foreach ($q in $parts) {
    if ($q.PostCode) { continue }
    $n = Norm $q.Company; if ($n.Length -lt 3) { continue }
    $k = [math]::Min(12, $n.Length)
    $hit = $page | Where-Object { $_.PostCode -and ((Norm $_.Company).Contains($n.Substring(0, $k)) -or ($_.Company -and $n.Contains((Norm $_.Company).Substring(0, [math]::Min(12, (Norm $_.Company).Length))))) } | Select-Object -First 1
    if ($hit) { $q.PostCode = $hit.PostCode; $q.City = $hit.City; if (-not $q.Country) { $q.Country = $hit.Country } }
  }
  return $parts
}
Write-Host "Etape 2 : participants de chaque projet"
New-Item -ItemType Directory -Force -Path "aramis_cache_v4" | Out-Null
$mode = "ws"; $wsFails = 0
$out = New-Object System.Collections.ArrayList
$i = 0; $nNew = 0; $t0 = Get-Date
foreach ($p in $projects) {
  $i++
  $cache = Join-Path "aramis_cache_v4" ($p.Id + ".json")
  $parts = $null
  if (Test-Path $cache) { $raw = Get-Content $cache -Raw -Encoding UTF8 | ConvertFrom-Json; $parts = @($raw | ForEach-Object { $_ }) }
  else {
    if ($mode -eq "ws") {
      $parts = Get-FromWs $p.Id
      if ($null -eq $parts) { $wsFails++; if ($wsFails -ge 2) { $mode = "page"; Write-Host "  service web indisponible : lecture des pages publiques Beteiligte" } }
      else { $parts = @($parts) }
    }
    if ($null -eq $parts) {
      try { $parts = @(Get-FromPage $p.Id) } catch { Write-Warning "  $($p.ProjectNumber) : echec ($($_.Exception.Message)), on continue"; Pause-Short; Pause-Short; continue }
    }
    ConvertTo-Json -InputObject @($parts) -Depth 4 | Set-Content -Path $cache -Encoding UTF8
    $nNew++; Pause-Short
  }
  foreach ($q in $parts) {
    [void]$out.Add([pscustomobject]@{ ProjectNumber = $p.ProjectNumber; AramisId = $p.Id; KindOfParticipation = $q.KindOfParticipation; Type = $q.Type; UID = $q.UID
      Company = $q.Company; PostCode = $q.PostCode; City = $q.City; Canton = $q.Canton; Country = $q.Country })
  }
  if ($Test) { Write-Host ("  " + $p.ProjectNumber + " (" + $p.Id + ") -> " + (($parts | ForEach-Object { "$($_.KindOfParticipation): $($_.Company) [$($_.UID)]" }) -join " | ")) }
  elseif ($i % 10 -eq 0) {
    $el = ((Get-Date) - $t0).TotalSeconds; $rest = if ($i -gt 0) { [int](($projects.Count - $i) * $el / $i / 60) } else { 0 }
    Write-Host ("  {0} / {1} projets lus ({2} en ligne) - environ {3} min restantes" -f $i, $projects.Count, $nNew, $rest)
  }
}
$out | Export-Csv -Path "innosuisse_participants.csv" -NoTypeInformation -Encoding UTF8
Write-Host "Termine : $($out.Count) participations ecrites dans innosuisse_participants.csv ($nNew projets lus en ligne)."
if ($Test) { Write-Host "Si un resultat semble faux, joignez les fichiers aramis_debug_*.html a la conversation." }
