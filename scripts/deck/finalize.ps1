# Finish the deliverable-7 deck in PowerPoint (Windows, PowerPoint installed):
#   1. open the pptxgenjs output in PowerPoint, replace the fallback font and save it again,
#   2. export the PDF copy and, if asked, one PNG per slide (to check fonts and layout),
#   3. print the fonts the slides use (the jury asked for fonts that work on every computer),
#   4. set the notes theme that PowerPoint adds (Calibri) to Arial, so only Arial is left.
# Usage (from prototype/):
#   powershell -File scripts/deck/finalize.ps1 docs/teslim/sunum/07-sunum.pptx docs/teslim/pdf/07-sunum.pdf [png dir]
param([string]$Pptx, [string]$Pdf, [string]$PngDir = "")

$Pptx = (Resolve-Path $Pptx).Path
$Pdf = [System.IO.Path]::GetFullPath($Pdf)

$tmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "deck-" + [guid]::NewGuid() + ".pptx")
$pp = New-Object -ComObject PowerPoint.Application
try {
    # PowerPoint counts a font it falls back to (Calibri) as used; replace it and write the whole file
    $p = $pp.Presentations.Open($Pptx, $false, $false, $false)
    try { $p.Fonts.Replace("Calibri", "Arial") } catch { }
    $p.SaveAs($tmp, 24)                       # ppSaveAsOpenXMLPresentation
    $p.Close()
    Move-Item -Force $tmp $Pptx
    $p = $pp.Presentations.Open($Pptx, $true, $false, $false)
    "PowerPoint fonts: " + ((@($p.Fonts) | ForEach-Object { "[" + $_.Name + "]" }) -join " ")
    $p.SaveAs($Pdf, 32)                       # ppSaveAsPDF
    if ($PngDir) {
        $PngDir = [System.IO.Path]::GetFullPath($PngDir)
        New-Item -ItemType Directory -Force $PngDir | Out-Null
        $i = 0
        foreach ($sl in $p.Slides) { $i++; $sl.Export((Join-Path $PngDir ("s{0:D2}.png" -f $i)), "PNG", 1600, 900) }
    }
    $p.Close()
}
finally { $pp.Quit() }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($Pptx, "Update")
try {
    $themes = @($zip.Entries | Where-Object { $_.FullName -like "ppt/theme/theme*.xml" })
    foreach ($e in $themes) {
        $r = New-Object System.IO.StreamReader($e.Open()); $xml = $r.ReadToEnd(); $r.Close()
        $new = $xml.Replace('typeface="Calibri Light"', 'typeface="Arial"').Replace('typeface="Calibri"', 'typeface="Arial"')
        if ($new -ne $xml) {
            $name = $e.FullName; $e.Delete()
            $w = New-Object System.IO.StreamWriter($zip.CreateEntry($name).Open(), (New-Object System.Text.UTF8Encoding($false)))
            $w.Write($new); $w.Close()
            "notes theme font set to Arial: $name"
        }
    }
    $fonts = @{}
    foreach ($e in $zip.Entries | Where-Object { $_.FullName -match "^ppt/(slides|slideMasters|slideLayouts|theme)/[^/]+\.xml$" }) {
        $r = New-Object System.IO.StreamReader($e.Open()); $xml = $r.ReadToEnd(); $r.Close()
        foreach ($m in [regex]::Matches($xml, '<a:latin typeface="([^"+][^"]*)"')) { $fonts[$m.Groups[1].Value] = 1 }
    }
    "latin fonts in slides, masters and themes: " + (($fonts.Keys | Sort-Object) -join ", ")
}
finally { $zip.Dispose() }
"wrote $Pptx and $Pdf"
