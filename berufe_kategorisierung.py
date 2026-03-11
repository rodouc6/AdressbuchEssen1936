#!/usr/bin/env python3
"""
Ordnet jeden eindeutigen normierten Berufseintrag einer von 12 Berufsgruppen zu.
Input:  berufe_unique_normiert_teilI.txt  (Vollformen, aus 'Beruf normiert')
Output: berufe_mapping.csv  (Beruf normiert, Berufsgruppe, Konfidenz)
"""
import csv, re
from pathlib import Path
from collections import Counter

INPUT  = Path("berufe_unique_normiert_teilI.txt")
OUTPUT = Path("berufe_mapping.csv")

REGELN = [
    # Bergbau & Hütte – zuerst, weil "Bergmann" sonst ggf. in "sonstige" fällt
    ("bergbau",    re.compile(
        r"bergmann|berginvalide|bergarbeiter|berginvalid|bergingenieur|bergassessor"
        r"|bergbau|bergwerks|bergtagelöhn"
        r"|\bhauer\b|steiger|reviersteiger|fahrsteiger|maschinensteiger"
        r"|grubenschlosser|grubenbeamt|grubenarb"
        r"|kokerei|koksarb|koksmeister|koksarbeiter"
        r"|hüttenarb|hüttenwerk|hochofen|schmelzer"
        r"|schachtmeister|schießmeister|richtmeister"
        r"|zechenarb|zechenbeamt|zechenarbeiter"
        r"|lampemeister|lampenmeister|kauenwärter|markenkontrolleur"
        r"|wiegemeister|holzmeister|fördermaschinen|förderaufseher"
        r"|brikettmeister|stocher|schleppjunge",
        re.I)),

    # Haushalt, Rente, Invalide
    ("haushalt",   re.compile(
        r"\binvalide\b|berginvalide|kriegsinvalide|reichsinvalide"
        r"|\brentner\b|\brentnerin\b|\bpensionär\b|\bpension\b"
        r"|hausfrau|\bwitwe\b|\bww\b"
        r"|arbeitslos|erwerbslos|berufslos"
        r"|\blandwirt\b|landwirtin|landwirtschaft"
        r"|hausmeister|hausmeisterin|hausbesitzer|hausbesitzerin",
        re.I)),

    # Freie Berufe & Akademiker
    ("akademisch", re.compile(
        r"\barzt\b|ärztin|zahnarzt|zahnärztin|tierarzt"
        r"|rechtsanwalt|rechtsanwältin|notar|notarin"
        r"|\bingenieur\b|bauingenieur|bergingenieur|oberingenieur|zivilingenieur"
        r"|diplom|doktor|dr\.\-ing|dr\.\-med"
        r"|apotheker|apothekenbesitzer"
        r"|\barchitekt\b|architek"
        r"|chemiker|laborant"
        r"|assessor|bergassessor|gerichtsassessor|studienassessor"
        r"|studienrat|studiendirektor|gymnasiallehrer|handelslehrer"
        r"|richter|staatsanwalt|syndikus|wirtschaftsprüfer"
        r"|landmesser|vermessungstechniker"
        r"|zahntechniker",
        re.I)),

    # Industrie & Handwerk (breit gefasst)
    ("industrie",  re.compile(
        r"\bschlosser\b|maschinenschlosser|werkzeugschlosser|autoschloss|grubenschlosser"
        r"|\bdreher\b|drehmeister"
        r"|\bschweißer\b|elektroschweißer"
        r"|\bmaurer\b|maurermeister|maurerpolier"
        r"|zimmermann|zimmermeister|zimmerpolier|zimmerer"
        r"|schreiner|schreinermeister|modellschreiner|maschinenschreiner"
        r"|\btischler\b|tischlermeister"
        r"|\bschmied\b|schmiedemeister"
        r"|\bklempner\b|klempnermeister"
        r"|monteur|elektromonteur|heizungsmonteur|automonteur"
        r"|\belektriker\b|elektromeister|elektrotechniker"
        r"|anstreicher|anstreichermeister|malermeister|\bmaler\b"
        r"|dachdecker|dachdeckermeister"
        r"|schuhmacher|schuhmachermeister|schuhm"
        r"|\bformer\b|formermeister|maschinenformer|kernmacher"
        r"|\bfräser\b|\bhobler\b|\bbohrer\b|\bpolierer\b|\bschleifer\b"
        r"|stuckateur|stukkateurmeister"
        r"|fliesenleger|rohrleger|linoleumleger|steinsetz"
        r"|buchbinder|buchbindermeister|buchbind"
        r"|buchdrucker|buchdruckermeister|schriftsetzer|maschinensetzer"
        r"|gärtner|gartenarbeiter|gartenmeister|gartenbau"
        r"|fabrikarbeiter|fabrikbeamter|fabrikant|fabrikdirektor|fabrikbesitzer"
        r"|\barbeiter\b|hilfsarbeiter|vorarbeiter|tagesarbeiter|lagerarbeiter"
        r"|bauarbeiter|bauhilfsarbeiter|tiefbauarbeiter|erdarbeiter"
        r"|metallarbeiter|holzarbeiter|glasarbeiter|wäschearbeiter"
        r"|maschinenarbeiter|montagearbeiter|transportarbeiter|platzarbeiter"
        r"|rottenarbeiter|gartenarbeiter|rangierarbeiter|ofenarb|scherenarb"
        r"|ziegeleiarbeiter|waldarbeiter|facharbeiter|landarbeiter|bankarb"
        r"|gemeindearbeiter|stadtarbeiter|güterboden|handlanger"
        r"|maschinist|maschinenwärter|motorwärter|kesselwärter|maschinentechniker"
        r"|installateur|installationsgeschäft"
        r"|polsterer|polstermeister|sattler|sattlermeister"
        r"|glaser|glasmacher|glasbläser|marmorschleifer"
        r"|kettenanschläger|gußputzer|maschinenformer"
        r"|werkmeister|werkführer|werkhelfer|schichtmeister"
        r"|kranführer|elektroschweißer|chemotechniker"
        r"|bäckermeister|metzgermeister|konditormeister"
        r"|schneidermeister|schneiderin|schneider"
        r"|korbmacher|uhrmacher|stellmacher|uhrmacher"
        r"|\bwächter\b|pförtner|portier|aufseher|nachtwächter"
        r"|hauswart|hausdien|hausdiener"
        r"|tagelöhner|bergtagelöhner|\bdiener\b"
        r"|meister\b|obermeister|hilfsmeister"
        r"|kalkulator|\bprüfer\b|maßprüfer"
        r"|walzmeister|brikettmeister|lagermstr|packmstr|hallenmstr"
        r"|schirrmstr|futtermstr|schirrmeister|futtermeister|hallenmeister"
        r"|bauzeichner|anzeichner|vorzeichner"
        r"|\btechniker\b|bautechniker|maschinentechniker|zahntechniker|elektrotechniker"
        r"|\bmechaniker\b|mechanikermstr|mechanikermeister"
        r"|stukkateur|stukkateurmeister"
        r"|\bgießer\b|schmelzer|\bwalzer\b|\bweber\b|\bnäherin\b|\bpacker\b"
        r"|\bpolier\b|bauführer|betriebsführer"
        r"|\bpflasterer\b|pflaster"
        r"|heißmangel|wäscherei|plätterei"
        r"|\blagerist\b|lagerhalter"
        r"|dekorateur|tapezier",
        re.I)),

    # Handel & Kaufleute
    ("handel",     re.compile(
        r"\bkaufmann\b|kauffrau|kaufmännisch"
        r"|\bhändler\b|großhändler|einzelhändler"
        r"|handlungsgehilfe|handelsmann|handelsvertreter|generalvertreter"
        r"|\bvertreter\b|\bmakler\b|reisender|handelsreisend"
        r"|kolonialwaren|tabakwaren|schreibwaren|milch(?:händler|handlung)"
        r"|gemüse(?:händler|handlung|geschäft)|obst(?:händler|handlung)"
        r"|kartoffel(?:händler|handlung)|kohlen(?:händler|handlung)"
        r"|holzhandlung|eisenwaren|papierwaren|kurzwaren|wollwaren"
        r"|manufakturwaren|textilwaren|schuhwaren|weißwaren|backwaren"
        r"|feinkostwaren|goldwaren|fischh(?:ändler|andlung)"
        r"|eierhandlung|lebensmittel(?:geschäft|handlung)"
        r"|buchhandlung|buchhändler|viehh(?:ändler|andlung)"
        r"|möbelhandlung|blumen(?:geschäft|handlung)"
        r"|zigarrengeschäft|maßgeschäft|friseurgeschäft|putzgeschäft"
        r"|photograph|fahrradhandlung|althandlung"
        r"|großhandlung|tabakwaren.großhandlung|obst.großhandlung"
        r"|\binhaber\b|inhaberin|fabrikant|fabrikbesitzer"
        r"|gutsbesitzer|hausbesitzer|trinkhallenbesitzer|apothekenbesitzer"
        r"|buchdruckerei.besitzer"
        r"|geschäftsführer|geschäftsinhaber|geschäftsinhaberin"
        r"|geschäfts(?:führer|inhaber)"
        r"|unternehmer|bauunternehmer|fuhrunternehmer|transportunternehmer"
        r"|tiefbauunternehmer|autovermietung|gartenbaubetrieb"
        r"|filialleiter|fuhrgeschäft|malergeschäft|baugeschäft"
        r"|anstreichergeschäft|stuckgeschäft|installationsgeschäft"
        r"|lebensmittelgeschäft",
        re.I)),

    # Verkehr & Transport
    ("verkehr",    re.compile(
        r"kraftwagen.?führer|lokomotiv|lokomotive.?führer"
        r"|fuhrmann|kraftfahrer"
        r"|straßenbahn|reichsbahn|eisenbahn"
        r"|\bschaffner\b|postschaffner|zugschaffner|stationsschaffner|ladeschaffner|kassenschaffner"
        r"|\bzugführer\b|rottenführer|kolonnenführer|wagenführer|rangierführer"
        r"|\brangierer\b|rangiermeister|rangieraufseher|rangierarbeiter"
        r"|bahnmeister|bahnarbeiter|bahnbeamter|bahnwärter|bahnhofsvorsteher"
        r"|weichensteller|weichenwärter|hilfsweichensteller|hilfsweichenwärter"
        r"|streckenwärter|oberbauarbeiter"
        r"|postbeamter|postassistent|postsekretär|postinspektor|posthelfer"
        r"|postaushelfer|postmeister|postamtmann|postbetriebs"
        r"|telegraphen|leitungsaufseher"
        r"|feuerwehrmann|brandmeister|fahrmeister|stellwerksmeister"
        r"|\bheizer\b|kesselheizer|lokomotivheizer"
        r"|\bkutscher\b|\bbeifahrer\b|laternenwärter"
        r"|\bbote\b|laufbursche"
        r"|spediteur|lagerhalter|fuhrgeschäft|fuhrunternehmer",
        re.I)),

    # Verwaltung & Beamte
    ("verwaltung", re.compile(
        r"\bbeamter\b|beamtin|bürobeamter|bankbeamter|zechenbeamter"
        r"|fabrikbeamter|syndikatsbeamter|kassenbeamter|aufsichtsbeamter"
        r"|verlagsbeamter|terminbeamter|revisionsbeamter|verwaltungsbeamter"
        r"|rechnungsbeamter|laboratoriums|vollzugs|vollziehungs|bergbaubeamter"
        r"|\bangestellter\b|angestellte|büroangestellter|bankangestellter|hotelangestellter"
        r"|\bsekretär\b|sekretärin|stadtsekretär|steuersekretär|zollsekretär"
        r"|postsekretär|obersekretär|stadtobersekretär|justizsekretär|kanzleisekretär"
        r"|\bbuchhalter\b|lohnbuchhalter"
        r"|\bdirektor\b|bankdirektor|fabrikdirektor|studiendirektor|musikdirektor"
        r"|\binspektor\b|stadtinspektor|stadtoberinspektor|bauinspektor|büroinspektor"
        r"|zollinspektor|postinspektor|steuerinspektor|montageinspektor|oberinspektor"
        r"|bürovorsteher|bürogehilfe|bürodiener|büroassistent"
        r"|hausmeister|hausmeisterin|schulhausmeister"
        r"|amtmann|stadtamtmann|postamtmann|amtsgehilfe"
        r"|kassierer|rendant|kontorist|prokurist|expedient"
        r"|\brevisor\b|bücherrevisor|rechnungsrevisor"
        r"|kontrolleur|straßenbahnkontrolleur"
        r"|lagerverwalter|magazinverwalter|wohnungsverwalter|materialienverwalter"
        r"|verwalter\b|lagerhalt"
        r"|stadtarbeiter|gemeindearbeiter"
        r"|stadtobersekretär|stadtinspektor"
        r"|syndikats|kanzlei|registrat|verwaltung"
        r"|bürgermeister|konrektor"
        r"|gelderheher|steuerberater|steuerassistent"
        r"|schriftleiter|versandleiter|betriebsleiter|filialleiter|abteilungsleiter"
        r"|abteilungsvorsteher|konsumvorsteher|bahnhofsvorsteher"
        r"|werkführer|betriebsführer|gruppenführer",
        re.I)),

    # Gastgewerbe, Lebensmittelhandwerk, Körperpflege
    ("gastro",     re.compile(
        r"\bgastwirt\b|schankwirt|\bwirt\b|gasthof|gasthaus"
        r"|\bkellner\b|kellnerin|\bkoch\b|köchin"
        r"|\bkonditor\b|konditormeister"
        r"|\bbäcker\b|bäckermeister|bäckerei"
        r"|\bmetzger\b|metzgermeister|fleischer|fleischerei"
        r"|\bbrauer\b|braumeister|weinhandl|spirituosen"
        r"|zigarrenhändler|zigarrengeschäft"
        r"|\bfriseur\b|friseurin|friseurmeister|friseurgeschäft|barbier|coiffeur"
        r"|\bmetzgerei\b|fleischerei|bäckerei",
        re.I)),

    # Bildung, Kirche & Kultur
    ("bildung",    re.compile(
        r"\blehrer\b|lehrerin|hauptlehrer|mittelschullehrer|musiklehrer"
        r"|handelslehrer|gewerbe.ober.lehrer|gymnasiallehrer"
        r"|\bpfarrer\b|\bdiakon\b|\bkantor\b|\bküster\b"
        r"|prediger|priester|kaplan|missionar"
        r"|rektor|konrektor|schulrat|studiendirektor|studienrat"
        r"|\bmusiker\b|musikdirektor|kapellmeister|organist"
        r"|konzertmeister|sänger|schauspieler"
        r"|erzieher|erzieherin",
        re.I)),

    # Militär & Polizei
    ("militär",    re.compile(
        r"\bsoldat\b|wachtmeister|hauptwachtmeister|hilfswachtmeister"
        r"|\bleutnant\b|\bhauptmann\b|\bfeldwebel\b"
        r"|polizei|polizist|gendarm|schutzpolizei|kriminalpolizei|kriminal"
        r"|reichswehr|\boffizier\b",
        re.I)),

    # Soziales & Gesundheit
    ("sozial",     re.compile(
        r"krankenpfleger|krankenschwester|krankenpflegerin|krankenwärter"
        r"|hebamme|heilgehilfe|heildiener"
        r"|fürsorger|fürsorge|wohlfahrt|sanitäts|rotkreuz|diakonisse",
        re.I)),
]


def klassifiziere(beruf: str) -> str:
    for gruppe, pattern in REGELN:
        if pattern.search(beruf):
            return gruppe
    return "sonstige"


def main():
    berufe = [l.strip() for l in INPUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    stats = Counter()
    rows = []
    for b in berufe:
        g = klassifiziere(b)
        stats[g] += 1
        rows.append({"Beruf": b, "Berufsgruppe": g, "Konfidenz": "auto"})

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Beruf", "Berufsgruppe", "Konfidenz"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows):,} Einträge klassifiziert → {OUTPUT}")
    print("\nVerteilung (eindeutige Einträge):")
    for g, n in stats.most_common():
        pct = n / len(rows) * 100
        print(f"  {g:<15} {n:>5}  ({pct:.1f}%)")


if __name__ == "__main__":
    main()
