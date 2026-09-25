# Vanshavali (वंशावली) - Indian Family Tree Builder

A comprehensive web application for building and managing Indian family trees with cultural-specific features.

## 🎯 Overview

Vanshavali is a modern genealogy platform specifically designed for Indian families, incorporating traditional cultural markers like Gotra, Kuladevata, Nakshatra, and joint family structures that Western genealogy software typically ignores.

## ✨ Key Features

### 1. **Multi-View Family Tree Visualization**

#### Cluster View
- Visualizes joint family households
- Shows family members grouped by location
- Displays household heads and member roles
- Marriage connections with heart icons

#### Pedigree View
- Traditional vertical family tree
- Shows parent-child relationships with labels (Son/Daughter)
- Marriage connections between spouses
- Hierarchical generation display

#### List View
- Generation-based listing
- Shows spouses and children inline
- Easy navigation through family members
- Compact view for large families

#### Relations View (NEW!)
- **Comprehensive relationship detection** for any selected person
- Automatically identifies 15+ relationship types:
  - Spouse (Husband/Wife)
  - Parents (Father/Mother)
  - Children (Son/Daughter)
  - Siblings (Brother/Sister)
  - Grandparents (Paternal/Maternal)
  - Grandchildren (Grandson/Granddaughter)
  - Uncles & Aunts (Chacha/Tau/Bua/Mama/Mami)
  - Nephews & Nieces (Bhatija/Bhanja/Bhatiji/Bhanji)
  - Cousins (Cousin Brother/Sister)
  - In-Laws (Father-in-law, Mother-in-law, Brother-in-law, Sister-in-law, Son-in-law/Damad, Daughter-in-law/Bahu)
- Color-coded relationship badges
- Grouped by relationship category
- Hindi/Indian terms included

### 2. **Indian Cultural Data Model**

#### Gotra (Lineage/Clan)
- Supports 10 major Gotras (Kashyapa, Bharadwaj, Vashishtha, etc.)
- Gotra compatibility checker for matrimonial purposes
- Prevents Sagotra (same-clan) marriages

#### Kuladevata (Family Deity)
- Records family patron deity
- Maps temple locations
- Groups families by shared deities
- Helps discover ancestral connections

#### Astrological Data
- Nakshatra (Birth Star) - 27 stars supported
- Rashi (Zodiac Sign) - 12 signs supported
- Kula (Dynasty) - Suryavanshi, Chandravanshi, etc.
- Jati (Sub-caste) - Flexible text field
- Pravara (Sacred lineage) - Optional field

#### Ancestral Location
- Village, District, State tracking
- Kuladevata Temple mapping
- Helps reconnect with distant relatives

### 3. **Member Management**

#### Add Member Form
- Comprehensive form with 5 sections:
  1. Basic Information (name, gender, birth/death dates)
  2. Indian Cultural Details (Gotra, Nakshatra, Kuladevata, etc.)
  3. Ancestral Location (village, district, state)
  4. Family Relationships (father, mother selection)
  5. Additional Details (occupation, education, notes)
- Native script support (Tamil, Devanagari, etc.)
- Privacy controls for living relatives

#### Member List
- Searchable table with filters
- Filter by gender, living status
- Sort by name, birth date, Gotra
- Phonetic search for Indian names
- Quick access to member details

### 4. **Matrimonial Biodata Generator** (NEW!)

Generate traditional Indian matrimonial biodata with:
- **Personal Details**: Name, DOB, birthplace, gender
- **Horoscope Details**: Gotra, Kula, Nakshatra, Rashi, Kuladevata
- **Education & Profession**: Qualifications, occupation
- **Family Details**: Parents' names and occupations, siblings
- **Ancestral Details**: Village, district, state, temple
- **Contact Details**: Phone, email, address
- **Expectations**: Partner preferences
- **Photo placeholder** (optional)
- Traditional formatting with Om symbol and Sanskrit headers
- Print and PDF download options
- Customizable sections (include/exclude photos, horoscope, family details)

**Access Points:**
- Dashboard: "Generate Biodata" card with member selector
- Person Detail page: "Generate Biodata" button (for living members)

### 5. **Advanced Search**

#### Phonetic Search
- Handles Indian name spelling variations
- Examples: Mukherjee = Mukerji = Mukhopadhyay
- Vowel variations: Krishna = Krsna
- Aspirated consonants: Bharadwaj = Baradwaj
- Transliteration support

#### Multi-Field Search
- Search by name, Gotra, village, Kuladevata, or Nakshatra
- Filter by specific field type
- Toggle phonetic matching on/off
- Real-time results

### 6. **Gotra & Kuladevata Management**

#### Gotra Compatibility Checker
- Select two individuals
- Checks if they share the same Gotra
- Prevents Sagotra marriages
- Shows detailed compatibility result
- Educational information about Gotra rules

#### Gotra Distribution
- Visual breakdown of Gotras in family
- Member count per Gotra
- Quick reference for family composition

#### Kuladevata Mapping
- Groups families by shared deity
- Shows temple locations
- Helps discover ancestral connections
- Visual deity distribution map

### 7. **Privacy & Access Control**

- Mark living relatives as "Private"
- Private members hidden from non-family viewers
- Role-based access control ready
- Privacy indicators on all views

### 8. **Dashboard**

- Family overview with statistics
- Total members, households, states, Gotras
- Quick action cards for main features
- Recent members list
- Household distribution by location
- Cultural information display

## 🎨 Design Features

- **Color Scheme**: Warm amber/saffron theme reflecting Indian culture
- **Bilingual Navigation**: English with Hindi labels
- **Responsive Design**: Works on desktop and mobile
- **Custom Scrollbars**: Themed to match the app
- **Smooth Animations**: Fade-in effects and transitions
- **Print-Ready**: Biodata optimized for printing

## 📊 Sample Data

Includes a realistic 20-member South Indian Iyer family:
- **4 Generations**: Grandparents to great-grandchildren
- **6 Households**: Across Chennai, Madurai, Bangalore, Mumbai, Hyderabad, California
- **Cultural Diversity**: Multiple Gotras, Kuladevatas, and locations
- **Realistic Details**: Occupations, education, astrological data

## 🛠️ Technical Stack

- **Frontend**: React 18 + TypeScript
- **Styling**: Tailwind CSS 4
- **Build Tool**: Vite
- **Icons**: Lucide React
- **State Management**: React Hooks
- **Type Safety**: Full TypeScript implementation

## 📁 Project Structure

```
src/
├── components/
│   ├── AddPerson.tsx          # Add member form
│   ├── BiodataGenerator.tsx   # Matrimonial biodata (NEW!)
│   ├── Dashboard.tsx          # Main dashboard
│   ├── FamilyTree.tsx         # Tree visualization with relations (ENHANCED!)
│   ├── GotraView.tsx          # Gotra & Kuladevata management
│   ├── MemberList.tsx         # Member table with filters
│   ├── PersonDetail.tsx       # Detailed person view with all relations (ENHANCED!)
│   ├── SearchView.tsx         # Advanced search with phonetic matching
│   └── Sidebar.tsx            # Navigation sidebar
├── data/
│   └── sampleData.ts          # Sample family data
├── types.ts                   # TypeScript interfaces
├── App.tsx                    # Main app component
├── main.tsx                   # Entry point
└── index.css                  # Global styles
```

## 🚀 Getting Started

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## 🎯 Use Cases

1. **NRI Families**: Document roots for western-born children
2. **Matrimonial Purposes**: Generate biodatas and check Gotra compatibility
3. **Cultural Preservation**: Record Kuladevata, Gotra, and ancestral villages
4. **Family Reunions**: Visualize joint family structures
5. **Genealogy Research**: Track lineage across generations
6. **Property & Inheritance**: Document family connections for legal purposes

## 🌟 Unique Indian Features

Unlike Western genealogy software, Vanshavali includes:
- ✅ Gotra-based marriage compatibility
- ✅ Kuladevata (family deity) tracking
- ✅ Nakshatra/Rashi (astrological data)
- ✅ Joint family household visualization
- ✅ Matrilineal system support (Tharavad)
- ✅ Native script name support
- ✅ Ancestral village mapping
- ✅ Traditional biodata generation
- ✅ Hindi/Indian relationship terms
- ✅ Phonetic search for Indian names

## 📝 Future Enhancements (Roadmap)

- [ ] GEDCOM 7.0 import/export with Indian extensions
- [ ] Graph database integration (Neo4j)
- [ ] Bahi (Panda) registry integration
- [ ] Ancestral property records attachment
- [ ] Multi-language UI (Hindi, Tamil, Telugu, Bengali, Marathi)
- [ ] Mobile app version
- [ ] Cloud sync and collaboration
- [ ] DNA integration for verification
- [ ] Historical record scanning (OCR)
- [ ] Community features for connecting with distant relatives

## 🙏 Cultural Sensitivity

This application respects and celebrates Indian cultural diversity:
- Supports both patriarchal and matrilineal systems
- Acknowledges regional variations in naming conventions
- Respects privacy of living relatives
- Provides educational information about cultural practices
- Inclusive of all Indian communities and traditions

## 📄 License

This is a demonstration project built for educational purposes.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

---

**Built with ❤️ for preserving Indian family heritage**

॥ वसुधैव कुटुम्बकम् ॥
"The world is one family"
