# Searchable fields catalogue (autocomplete / combobox inventory)

Status: proposal (design reference — no code or schema change yet). Date: 2026-10-06.

Which form fields in Vanshavali should be searchable comboboxes, what each suggests, where the
vocabulary comes from, and which fallback values each must offer. It builds on what already exists:

| Already in the codebase | Where |
|---|---|
| ARIA 1.2 combobox (async options, live result count, keyboard nav) | `frontend/src/components/ui/Combobox.tsx` |
| Person and place pickers (search-as-you-type against the tree) | `frontend/src/components/pickers.tsx` |
| Place hierarchy, `place_type`, `lgd_code`, local + historical names, trigram search index | `backend/app/models/genealogy.py` (`Place`) |
| Jyotish vocabularies with aliases in Latin, Devanagari, Tamil, Telugu (nakshatra, rashi, tithi, paksha) | `backend/app/modules/astrology/vocab.py` |
| Typing-aid lists: gotras (15), kulas (8), rashis, nakshatras | `frontend/src/data/masterData/*` |
| Fallback statuses: `known`, `unknown`, `not_applicable`, `withheld` | `ValueStatus` in `backend/app/models/enums.py` |
| Regional kinship terms derived from relationship chains | `frontend/src/lib/kinship.ts` |

## Ground rules that every field below follows

1. **Suggest, never force.** A vocabulary is a typing aid (CLAUDE.md: master data is "never used to
   infer values"). Every combobox ends with a *"Use '‹typed text›' as written"* option. Family
   memory, regional spelling and old documents beat a canonical list.
2. **Store the code *and* what the user typed.** Save `{vocab_code | null, value_as_recorded}`,
   as `PlaceValue` already does with `place_id` + `place_as_recorded`. Labels can then be renamed
   or translated without rewriting data, and provenance survives.
3. **Fallbacks are statuses, not list items.** "Unknown", "Not applicable" and "Prefer not to
   disclose" map to `ValueStatus.unknown`, `not_applicable` and `withheld`. Show them as three
   small chips under the input instead of rows in the list, so search can't hide them and
   reports can tell "we don't know" apart from "we won't say".
4. **No derivation.** Do not fill rashi from nakshatra, pravara from gotra, state from district
   or Chacha/Tau from age guesses. Show suggestions; the human confirms.
5. **Under about 7 options, use radios or a segmented control, not a combobox** (paksha, sex at birth,
   lineage, date qualifier).

## Field catalogue

Legend for **Fallback**: `U` = Unknown, `NA` = Not applicable, `W` = Prefer not to disclose
(`withheld`), `AR` = "Use as written" free text.

### 1. Cultural and religious

| Category | Field | Dropdown / autocomplete behaviour | Standard options / data source | Fallback / privacy |
|---|---|---|---|---|
| Cultural | **Gotra** | Searchable, alias- and script-tolerant (Bhardwaj → Bharadwaj, भारद्वाज). Rank values already used in this tree first, then values common in the selected community, then all. Never filtered out by community. | Curated gotra vocabulary (expand `gotras.ts` from 15 to about 150, see Appendix A), each with aliases and native-script names, plus community clan-gotra sets (e.g. Agrawal's 18, Jat, Khatri, Jain, Sikh clans) tagged by community. Tree-local additions are suggested back to that tree only. | U, NA, W, AR |
| Cultural | **Pravara** | Searchable. Once a gotra is chosen, its listed pravara is shown first as a hint, never auto-filled. | Pravara strings attached to the gotra vocabulary. | U, NA, W, AR |
| Cultural | **Kula / Vamsha** | Searchable short list. | `kulas.ts` (Suryavanshi, Chandravanshi, Agnivanshi, Nagavanshi, Ikshvaku, Yaduvanshi, …). | U, NA, W, AR |
| Cultural | **Kuladevata / Kuladevi** | Two-part entry: (a) deity name, a searchable seed list ranked by tree usage and ancestral region; (b) optional **shrine**, a `PlacePicker` limited to `place_type = temple/shrine`. Same deity + different shrine = a different kuladevata. | Seed list of pan-Indian deities and major kuladevi shrines (Appendix B). Most values will be tree-specific. Any value used in a tree becomes a suggestion in that tree. No global crowd list without moderation. | U, NA, W, AR |
| Cultural | **Religion** | Searchable short list. | Census of India religion categories (Hindu, Muslim, Christian, Sikh, Buddhist, Jain, Parsi/Zoroastrian, Jewish, Bahá'í, tribal/indigenous faiths: Sarna, Donyi-Polo, Sanamahi, …), "Other". | U, W, AR |
| Cultural | **Sampradaya / sect** | Searchable, filtered by religion when set. | Curated (Shaiva, Vaishnava, Shakta, Smarta, Swaminarayan, Pushtimarg, Lingayat, Shvetambara, Digambara, Sunni, Shia, Bohra, …). | U, NA, W, AR |
| Cultural | **Community / Jati** | **Tree-local suggestions only.** No national caste list. | Values already entered in this tree. A national list is politically contested, privacy-sensitive and would push labels on families. | U, NA, W, AR. `W` is offered prominently. |
| Cultural | **Ancestral village / Tharavad / house name** | Village → `PlacePicker` (see §3). House/tharavad name → tree-local suggestions. | Gazetteer + tree. | U, AR |
| Astrology | **Rashi (moon sign)** | Searchable; matches Sanskrit, Hindi, Tamil/Telugu and the Western-sign gloss. Show "Mesha · मेष · (Aries)". | 12 rashis (Appendix C), from `astrology/vocab.py`. Label as *sidereal moon sign* so users don't enter their newspaper sun sign. | U, W |
| Astrology | **Nakshatra** | Searchable with aliases (Thiruvathirai → Ardra, Pooram → Purva Phalguni). | 27 nakshatras (Appendix C), from `vocab.py`. Optional Abhijit as the 28th, behind a setting. | U, W |
| Astrology | **Nakshatra pada** | Segmented 1 / 2 / 3 / 4. | Fixed. | U |
| Astrology | **Lagna (ascendant)** | Same list as Rashi. | 12 rashis. | U, W |
| Astrology | **Ayanamsha** | Short select. | Lahiri (default), Raman, KP, Fagan-Bradley, other (`vocab.py`). | U |

### 2. Temporal

| Category | Field | Dropdown / autocomplete behaviour | Standard options / data source | Fallback / privacy |
|---|---|---|---|---|
| Date | **Calendar system** | Short select; decides which month list the next field shows. | Gregorian, Vikram Samvat, Shaka (national), Hijri, Tamil solar, Bengali (Bangabda), Malayalam (Kollam), Nanakshahi, Other. | U |
| Date | **Month** | Searchable within the chosen calendar. Accepts English, Hindi, regional and colloquial names (Sawan, Bhadon, Kwar, Agahan, Poos). | Gregorian 12 (English + Hindi). Hindu lunar 12 + **Adhik / Purushottam maas**. Tamil, Bengali and Malayalam solar months (Appendix D). For lunar months, ask **Amanta vs Purnimanta**: Krishna-paksha dates fall in different named months in North and South India. | U |
| Date | **Paksha** | Segmented control: Shukla (Sudi) / Krishna (Badi/Vadi). | 2 values (`vocab.py`). Accept *Sudi / Badi* aliases, which are common in Hindi records. | U |
| Date | **Tithi** | Searchable 1–15 with names. Option 15 shows Purnima under Shukla and Amavasya under Krishna. | 15 tithis + Purnima/Amavasya (Appendix D), from `vocab.py`. | U |
| Date | **Year era** | Number input + era select (CE, VS, Shaka, Hijri, Bangabda, Kollam). Show the CE equivalent as a hint (VS − 57/56) but **do not convert silently**. | Fixed. | U |
| Date | **Date qualifier** | Segmented: Exact / About / Before / After / Between / Estimated. | GEDCOM date modifiers. | — |
| Date | **Day of week (var)** | 7-item select (Ravivar … Shanivar), only when the source records it. | Fixed. | U |

### 3. Geographical

All place fields use the **existing `PlacePicker`**: a search against the tree's `place` table first,
then a gazetteer lookup that *creates* a tree place (with `lgd_code`, `parent_place_id` and
`geocoding_source`) when the user picks a gazetteer result.

| Category | Field | Dropdown / autocomplete behaviour | Standard options / data source | Fallback / privacy |
|---|---|---|---|---|
| Location | **Country** | Searchable, client-side list (about 250). Labels localised (भारत / India). India, Nepal, Pakistan, Bangladesh, Sri Lanka, UAE, UK, USA, Canada pinned first. Historical entities shown with dates: *British India (–1947)*, *East Pakistan (1947–71)*, *Burma*, *Ceylon*. | ISO 3166-1 codes + Unicode CLDR localised names (Hindi and other Indic names included). | U, AR |
| Location | **State / UT** | Searchable, shown when country = India (or a neighbour with states). Old names map to current ones *and* can be stored as historical: Bombay State, Madras, Mysore, United Provinces, Hyderabad State, princely states. | 28 states + 8 UTs (Appendix E); LGD state codes. | U, AR |
| Location | **District** | **Dynamic, cascaded from state.** If state is set, filter to it (one state = at most ~75 districts, client-side). If state is empty, search all (~780, still small enough to load) and show "District, State" so choosing a district can *suggest* the state. Districts that were split or renamed keep `historical_names` + `date_validity` ("Allahabad → Prayagraj, 2018"). | **LGD (Local Government Directory, lgdirectory.gov.in)**: authoritative codes for states, districts, sub-districts, blocks, villages, with a change history. Use a versioned snapshot in our DB, not a live call per keystroke. Census 2011 codes kept for mapping old records. | U, AR |
| Location | **Tehsil / Taluka / Mandal / Sub-division** | Cascaded from district. Label adapts per state (Tehsil, Taluka, Mandal, Circle). | LGD sub-district master (~7k). | U, AR |
| Location | **Village / Town / City** | **Server-side** search (pg_trgm, debounced), scoped to district → state → country when set. Every result shows its hierarchy ("Rampur · Rampur dist. · UP"; there are hundreds of Rampurs). | LGD villages (~6.5 lakh) + Census statutory and census towns for India. **GeoNames** (`cities500`, CC-BY) for the rest of the world. Optional geocoding (lat/long) through a self-hosted **Nominatim/OSM** server. Avoid sending ancestral addresses of living people to commercial APIs (privacy, ADR-0015 coordinate privacy). | U, AR (village names in old records are often spelled very differently; keep the as-recorded text) |
| Location | **Temple / Shrine / Ancestral house / Land parcel** | `PlacePicker` filtered by `place_type`, tree-local. | Tree's places. | U, W (for living households) |
| Location | **Migration "from → to"** | Two `PlacePicker`s plus a year range. | As above. | U |

### 4. Relationship, personal and demographic

| Category | Field | Dropdown / autocomplete behaviour | Standard options / data source | Fallback / privacy |
|---|---|---|---|---|
| Relationship | **Relationship type (stored)** | Short select. This is what is saved: primitive edges only (ADR-0003). | `RelationshipType`: biological / adoptive / step / foster parent, guardian, spouse, partner, divorced / separated spouse, sibling, other. | NA |
| Relationship | **"Add a relative" quick-add (Indian kin term)** | Searchable list of kin terms in English + Hindi (+ regional later): typing *chacha*, *चाचा* or *father's brother* finds it. Picking one expands it into the primitive edges it implies (Chacha → sibling of father) and creates placeholder people where needed. When the term depends on relative age (Tau vs Chacha, Jeth vs Devar), ask "elder or younger than ‹father›?" with **"Don't know"**. Never guess. | Kin-term table (Appendix F), extended from `lib/kinship.ts`. **Needs an ADR before building** (relationship modelling): where relative birth order is recorded, and how placeholder parents are created. | U (birth order), NA |
| Relationship | **Lineage** | Segmented. | biological / legal / ritual / social (`Lineage`). | U |
| Personal | **Given name / Surname** | Free text with suggestions from names *already in this tree* (surnames especially), plus a transliteration hint (type "sharma" → offer शर्मा for the Devanagari name field). | Tree. **No global name list.** | — |
| Personal | **Name type** | Short select. | `NameType`: birth, married, alias, religious, professional, nickname, transliteration, historical. | — |
| Personal | **Title / honorific** | Searchable short list. | Shri, Smt., Kumari, Pandit, Thakur, Sardar, Begum, Mirza, Dr., Late (स्व.), Ustad, … | NA, AR |
| Personal | **Sex at birth** | Radio (not a combobox). | `SexAtBirth`. | U, W |
| Personal | **Occupation** | Searchable; English + Hindi; ranked by tree usage. Include historical and agrarian occupations (Zamindar, Patwari, Lambardar, Kisan, Vaidya, Purohit, Munshi). | NCO-2015 (National Classification of Occupations) titles as the backbone + a curated historical list. | U, NA, AR |
| Personal | **Education / qualification** | Searchable. | Curated levels (Primary … Doctorate) + common degrees (B.A., M.B.B.S., B.Tech, …). | U, NA, W, AR |
| Personal | **Marriage rite / type** | Searchable short list. | Hindu (Vedic / Arya Samaj), Anand Karaj, Nikah, Christian, Special Marriage Act (civil), customary/tribal, Other. | U, W, AR |
| Life event | **Event type** | Searchable (many values). | `EventType` + `LifeEventCategory` (birth, mundan, upanayana, vivah, gauna, migration, death, shraddha, …). | — |
| Life event | **Cause of death** | Free text only. No suggestions: sensitive and low value. | — | U, W |
| Language | **Primary language / languages spoken** | Searchable multi-select; English + endonym (Marathi · मराठी). Stored as BCP-47 / ISO 639 codes (`primary_language` is `String(16)`). | 22 Eighth Schedule languages + English + major unscheduled ones (Appendix G). | U, AR |
| Language | **Script(s)** | Searchable multi-select; option rendered *in its own script*. Includes historical scripts used in land and genealogy records (Kaithi, Modi, Mahajani/Muriya, Landa, Sharada, Grantha). | ISO 15924 codes (`scripts_used`, `String(20)`). | U |

### 5. Sources, documents and property (genealogy-specific)

| Category | Field | Dropdown / autocomplete behaviour | Standard options / data source | Fallback |
|---|---|---|---|---|
| Source | **Source type / document category** | Searchable (long enum). | `SourceType`, `DocumentCategory` (incl. *pandit's bahi at Haridwar/Gaya/Pushkar*, *Khatauni*, *Jamabandi*, *7/12 extract*, *Patta*). | — |
| Source | **Repository / Teerth purohit record keeper** | Tree-local suggestions + place picker for the tirtha. | Tree. | U, AR |
| Property | **Land unit** | Searchable, filtered by state (bigha differs by state). | `property/units.py`. | AR |
| Property | **Revenue record term** | Searchable glossary (khasra, khata, khatauni, survey no., gat no.). | Curated, state-tagged. | AR |

## Appendices: standard option lists

### A. Gotra seed list (needs community review; aliases abbreviated)

Pan-Indian rishi gotras: Agastya, Angirasa, Atreya/Atri, Bharadwaj, Bhargava (Bhrigu), Dhananjaya,
Garga, Gautama, Harita, Jamadagni, Kanva, Kapila, Kashyapa, Kaundinya, Kaushika, Katyayana, Kutsa,
Lohita, Markandeya, Maudgalya (Mudgal), Parashara, Pulastya, Sankriti, Shandilya, Shaunaka,
Srivatsa, Upamanyu, Vadhula, Vashishtha, Vatsa, Vishnuvardhana, Vishwamitra.

Example community clan gotras (tag by community; non-exhaustive): **Agrawal (18):** Airan, Bansal,
Bindal, Bhandal, Dharan, Garg, Goyal, Goyan, Jindal, Kansal, Kuchhal, Madhukul, Mangal, Mittal,
Nangal, Singhal, Tayal, Tingal. **Others:** Jat, Gujjar, Ahir/Yadav, Khatri, Rajput (with *khanp*),
Maheshwari (72 khaps), Oswal/Jain, Kayastha subgroups. Load these from a reviewed data file, not hand-coded.

### B. Kuladevata / Kuladevi seed list (deity · well-known shrine)

Khandoba · Jejuri; Tulja Bhavani · Tuljapur; Mahalakshmi · Kolhapur; Renuka · Mahur; Ekvira · Karla;
Saptashrungi · Vani; Vaishno Devi · Katra; Jwala Ji · Kangra; Naina Devi; Chintpurni; Sharda · Maihar;
Vindhyavasini · Vindhyachal; Kamakhya · Guwahati; Karni Mata · Deshnok; Jeen Mata · Sikar; Shakambhari ·
Saharanpur/Sambhar; Ashapura · Kutch; Ambaji; Bahuchara · Becharaji; Khodiyar; Chamunda · Chotila;
Mookambika · Kollur; Chamundeshwari · Mysuru; Bhagavathi (Kodungallur, Chottanikkara); Ayyanar /
Kula deivam (Tamil Nadu); Venkateshwara · Tirumala; Manjunatha · Dharmasthala; Kalika; Dakshina Kali;
Ganesh, Hanuman, Bhairav, Shiva (local forms), Gram devata. Ranking: tree usage → ancestral-state
match → alphabetical.

### C. Rashis (12) and Nakshatras (27)

| # | Rashi | हिन्दी | Western gloss |
|---|---|---|---|
| 1 | Mesha | मेष | Aries |
| 2 | Vrishabha | वृषभ | Taurus |
| 3 | Mithuna | मिथुन | Gemini |
| 4 | Karka | कर्क | Cancer |
| 5 | Simha | सिंह | Leo |
| 6 | Kanya | कन्या | Virgo |
| 7 | Tula | तुला | Libra |
| 8 | Vrishchika | वृश्चिक | Scorpio |
| 9 | Dhanu | धनु | Sagittarius |
| 10 | Makara | मकर | Capricorn |
| 11 | Kumbha | कुम्भ | Aquarius |
| 12 | Meena | मीन | Pisces |

Nakshatras: 1 Ashwini अश्विनी · 2 Bharani भरणी · 3 Krittika कृत्तिका · 4 Rohini रोहिणी ·
5 Mrigashira मृगशिरा · 6 Ardra आर्द्रा · 7 Punarvasu पुनर्वसु · 8 Pushya पुष्य · 9 Ashlesha आश्लेषा ·
10 Magha मघा · 11 Purva Phalguni पूर्वा फाल्गुनी · 12 Uttara Phalguni उत्तरा फाल्गुनी · 13 Hasta हस्त ·
14 Chitra चित्रा · 15 Swati स्वाति · 16 Vishakha विशाखा · 17 Anuradha अनुराधा · 18 Jyeshtha ज्येष्ठा ·
19 Mula मूल · 20 Purva Ashadha पूर्वाषाढ़ा · 21 Uttara Ashadha उत्तराषाढ़ा · 22 Shravana श्रवण ·
23 Dhanishtha धनिष्ठा · 24 Shatabhisha शतभिषा · 25 Purva Bhadrapada पूर्वा भाद्रपद ·
26 Uttara Bhadrapada उत्तरा भाद्रपद · 27 Revati रेवती. (Tamil/Telugu aliases are in `vocab.py`.)

### D. Months, paksha, tithi

| # | Gregorian | हिन्दी | Hindu lunar (colloquial) | Tamil solar | Bengali | Malayalam |
|---|---|---|---|---|---|---|
| 1 | January | जनवरी | Chaitra चैत्र (Chait) | Chithirai | Boishakh | Chingam |
| 2 | February | फ़रवरी | Vaishakha वैशाख (Baisakh) | Vaikasi | Joishtho | Kanni |
| 3 | March | मार्च | Jyeshtha ज्येष्ठ (Jeth) | Aani | Asharh | Thulam |
| 4 | April | अप्रैल | Ashadha आषाढ़ (Asadh) | Aadi | Shrabon | Vrischikam |
| 5 | May | मई | Shravana श्रावण (Sawan) | Avani | Bhadro | Dhanu |
| 6 | June | जून | Bhadrapada भाद्रपद (Bhadon) | Purattasi | Ashshin | Makaram |
| 7 | July | जुलाई | Ashvin आश्विन (Kwar) | Aippasi | Kartik | Kumbham |
| 8 | August | अगस्त | Kartika कार्तिक | Karthigai | Ogrohayon | Meenam |
| 9 | September | सितंबर | Margashirsha मार्गशीर्ष (Agahan) | Margazhi | Poush | Medam |
| 10 | October | अक्टूबर | Pausha पौष (Poos) | Thai | Magh | Edavam |
| 11 | November | नवंबर | Magha माघ | Maasi | Falgun | Mithunam |
| 12 | December | दिसंबर | Phalguna फाल्गुन (Phagun) | Panguni | Choitro | Karkidakam |

The rows only number each calendar's own order; **the columns do not line up with each other.**
Hindu lunar list + **Adhik (Purushottam/Mal) maas**.

Paksha: Shukla शुक्ल (Sudi) · Krishna कृष्ण (Badi/Vadi).
Tithi: 1 Pratipada प्रतिपदा · 2 Dwitiya द्वितीया · 3 Tritiya तृतीया · 4 Chaturthi चतुर्थी ·
5 Panchami पंचमी · 6 Shashthi षष्ठी · 7 Saptami सप्तमी · 8 Ashtami अष्टमी · 9 Navami नवमी ·
10 Dashami दशमी · 11 Ekadashi एकादशी · 12 Dwadashi द्वादशी · 13 Trayodashi त्रयोदशी ·
14 Chaturdashi चतुर्दशी · 15 Purnima पूर्णिमा (Shukla) / Amavasya अमावस्या (Krishna).

### E. Indian States (28) and Union Territories (8), current as of 2026

States: Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chhattisgarh, Goa, Gujarat, Haryana,
Himachal Pradesh, Jharkhand, Karnataka, Kerala, Madhya Pradesh, Maharashtra, Manipur, Meghalaya,
Mizoram, Nagaland, Odisha, Punjab, Rajasthan, Sikkim, Tamil Nadu, Telangana, Tripura, Uttar Pradesh,
Uttarakhand, West Bengal.
UTs: Andaman and Nicobar Islands, Chandigarh, Dadra and Nagar Haveli and Daman and Diu, Delhi (NCT),
Jammu and Kashmir, Ladakh, Lakshadweep, Puducherry.
Historical (with validity dates): Bombay State, Madras State, Mysore State, Hyderabad State, United
Provinces, Central Provinces and Berar, PEPSU, Saurashtra, Travancore-Cochin, Madhya Bharat, Vindhya
Pradesh, Ajmer, Coorg, Bilaspur, Bengal/Punjab/Madras/Bombay Presidencies, princely states,
NWFP/Sindh/West Punjab (pre-1947).
The district list (~780) is **not hand-maintained**. Import it from an LGD snapshot with codes and
refresh it quarterly.

### F. Kin terms for quick-add (English · Hindi · primitive path)

Father पिता (parent♂) · Mother माता · Son बेटा · Daughter बेटी · Brother भाई · Sister बहन · Husband पति
· Wife पत्नी · Dada दादा (F·F) · Dadi दादी (F·M) · Nana नाना (M·F) · Nani नानी (M·M) · Pardada परदादा
· **Tau ताऊ (F·elder B)** · Tai ताई (Tau's wife) · **Chacha चाचा (F·younger B)** · Chachi चाची · Bua बुआ
(F·Z) · Phupha/Fufa फूफा (Bua's H) · Mama मामा (M·B) · Mami मामी · Mausi मौसी (M·Z) · Mausa मौसा ·
Bhatija भतीजा (B·S) · Bhatiji भतीजी · Bhanja भांजा (Z·S) · Bhanji भांजी · Pota पोता (S·S) · Poti
पोती · Nati नाती (D·S) · Natin नातिन · Sasur ससुर (Sp·F) · Saas सास (Sp·M) · **Jeth जेठ (H·elder B)**
· **Devar देवर (H·younger B)** · Jethani जेठानी · Devrani देवरानी · Nanad ननद (H·Z) · Nandoi ननदोई ·
Saala साला (W·B) · Saali साली (W·Z) · Saadhu साढ़ू (W·Z·H) · Jija जीजा (Z·H) · Bhabhi भाभी (B·W) ·
Damad दामाद (D·H) · Bahu बहू (S·W) · Samdhi समधी / Samdhan समधन (child's parent-in-law).
Bold = depends on relative age. Ask, offer "Don't know", never infer.

### G. Languages and scripts

Eighth Schedule (22): Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani,
Maithili, Malayalam, Manipuri (Meitei), Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi,
Tamil, Telugu, Urdu. Plus: English, Awadhi, Bhojpuri, Magahi, Bundeli, Chhattisgarhi, Garhwali,
Kumaoni, Haryanvi, Rajasthani/Marwari, Kutchi, Tulu, Kodava, Khasi, Mizo, Garo, Gondi, Bhili, Ho,
Kurukh, Persian (historical records).

Scripts (ISO 15924): Devanagari (Deva), Bengali-Assamese (Beng), Gurmukhi (Guru), Gujarati (Gujr),
Odia (Orya), Tamil (Taml), Telugu (Telu), Kannada (Knda), Malayalam (Mlym), Perso-Arabic/Nastaliq
(Arab), Ol Chiki (Olck), Meetei Mayek (Mtei), Latin (Latn), Tibetan (Tibt), Lepcha (Lepc);
historical: Kaithi (Kthi), Modi (Modi), Mahajani (Mahj), Landa/Khudawadi (Sind), Sharada (Shrd),
Takri (Takr), Grantha (Gran), Brahmi (Brah).

## UX best practices

1. **Forgiving matching.** Normalise both query and options: lower-case, strip diacritics and nukta,
   collapse vowel length (aa→a, ee→i, oo→u), common consonant swaps (v/w, sh/s, th/t, ph/f, ksh/x),
   doubled letters and trailing schwa ("Bhardwaj" = "Bharadwaja"). Rank: exact > prefix > alias >
   phonetic key > trigram fuzzy. Reuse the normaliser in `astrology/vocab.py` instead of writing a
   second one.
2. **Type in any script.** Match Devanagari and the other Indic aliases directly, and offer
   Hinglish → Devanagari transliteration (type `kashyap`, see कश्यप). Show both scripts in each row
   and highlight the matched alias ("Bhardwaj → **Bharadwaj**").
3. **Size decides where search runs.** Below ~1,000 items (gotras, rashis, months, countries,
   states, languages, even all ~780 districts): ship as lazily loaded JSON (dynamic `import()` or
   a cached `GET /api/v1/vocabularies/{name}` with `staleTime: Infinity`) and filter client-side
   on each keystroke. Large sets (villages ~6.5 lakh, world cities): server-side pg_trgm with
   150–250 ms debounce, minimum 2 characters, top 20 results, scoped by the parent fields, with
   request cancellation (TanStack Query `signal`) so late responses can't overwrite newer ones.
4. **Cascade without trapping.** State filters district, district filters tehsil and village. But
   picking a child first should *suggest* its parents (one click to accept), and changing a parent
   should flag dependent children ("Prayagraj isn't in Bihar — keep or clear?") instead of wiping
   them silently.
5. **One source of truth for vocabularies.** Today the astrology lists exist twice (backend
   `vocab.py`, frontend `masterData`). Serve them from the API with a version stamp and generated
   types, so validation and suggestion can't drift. Store codes, not labels.
6. **Context-aware ordering.** Values already used in this tree first, then recently picked by
   this user, then the regional/community match, then everything. This works especially well for
   surnames, gotra, kuladevata and villages, where one family repeats the same few values.
7. **Fallbacks always visible.** Unknown / Not applicable / Prefer not to disclose sit as chips
   outside the listbox (map to `ValueStatus`). "Use '‹text›' as written" is always the last option.
   Picking it is normal, not an error.
8. **Disambiguate homonyms.** Every place row shows its hierarchy and type; every deity row shows
   its shrine; every gotra row shows its community tag when one exists.
9. **Historical correctness.** Place and state names carry validity dates. When the event date is
   known, prefer the name valid *at that date* ("Bombay, 1952") and show the current name as a
   secondary line.
10. **Accessibility and mobile.** Keep the ARIA 1.2 pattern from `Combobox.tsx` (live result count,
    arrow keys, Esc, `lang` attribute on Indic options). On narrow screens open a full-height
    sheet with a 44 px row height. Don't open the on-screen keyboard for lists under 7 items; use
    radios or segmented controls instead.
11. **Privacy.** Caste/jati, religion and astrology for living people are sensitive. Suggestions
    from tree-local values must respect the authz redaction already applied server-side (never
    suggest a withheld value to a viewer who can't read it). Never send living people's addresses
    to third-party geocoders.
12. **Measure and improve.** Log (anonymously, by vocab name) how often "use as written" is
    chosen and what was typed. Frequent misses show which aliases to add or which vocab entries
    are missing.

## Follow-ups this would need

- ADR: kin-term quick-add (relative birth order, placeholder people) — relationship modelling.
- ADR: gazetteer import (LGD + GeoNames snapshot, versioning, historical names) — place modelling.
- `GET /api/v1/vocabularies/{name}` endpoint (typed schema, cached, versioned) + OpenAPI regen.
- Community review of the gotra and kuladevata seed lists before shipping.
