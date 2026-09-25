// Master data for Kulas (Dynasties)
export interface Kula {
  id: string;
  name: string;
  sanskritName: string;
  hindiName: string;
  alternativeNames: string[];
  meaning: string;
  origin: string;
  description: string;
}

export const kulas: Kula[] = [
  {
    id: 'kula-1',
    name: 'Suryavanshi',
    sanskritName: 'सूर्यवंशी',
    hindiName: 'सूर्यवंशी',
    alternativeNames: ['Suryavanshi', 'Solar Dynasty', 'Surya Vanshi', 'Ikshvaku'],
    meaning: 'Solar Dynasty',
    origin: 'Descended from Surya (Sun God) through Ikshvaku',
    description: 'The Solar Dynasty, descended from Lord Surya through King Ikshvaku. Lord Rama belonged to this dynasty.'
  },
  {
    id: 'kula-2',
    name: 'Chandravanshi',
    sanskritName: 'चन्द्रवंशी',
    hindiName: 'चन्द्रवंशी',
    alternativeNames: ['Chandravanshi', 'Lunar Dynasty', 'Chandra Vanshi', 'Somavanshi'],
    meaning: 'Lunar Dynasty',
    origin: 'Descended from Chandra (Moon God) through Budha',
    description: 'The Lunar Dynasty, descended from Lord Chandra (Moon God) through Budha. The Pandavas and Kauravas belonged to this dynasty.'
  },
  {
    id: 'kula-3',
    name: 'Agnivanshi',
    sanskritName: 'अग्निवंशी',
    hindiName: 'अग्निवंशी',
    alternativeNames: ['Agnivanshi', 'Fire Dynasty', 'Agni Vanshi', 'Agnikula'],
    meaning: 'Fire Dynasty',
    origin: 'Descended from Agni (Fire God)',
    description: 'The Fire Dynasty, said to have been born from the sacred fire at Mount Abu. Associated with Rajput clans.'
  },
  {
    id: 'kula-4',
    name: 'Nagavanshi',
    sanskritName: 'नागवंशी',
    hindiName: 'नागवंशी',
    alternativeNames: ['Nagavanshi', 'Serpent Dynasty', 'Naga Vanshi'],
    meaning: 'Serpent Dynasty',
    origin: 'Descended from the Nagas (serpent deities)',
    description: 'The Serpent Dynasty, descended from the Nagas. Prominent in Naga communities and some Northeast Indian tribes.'
  },
  {
    id: 'kula-5',
    name: 'Somavanshi',
    sanskritName: 'सोमवंशी',
    hindiName: 'सोमवंशी',
    alternativeNames: ['Somavanshi', 'Soma Dynasty'],
    meaning: 'Lunar Dynasty (alternate)',
    origin: 'Another name for Chandravanshi',
    description: 'Alternative name for the Lunar Dynasty, descended from Soma (Moon God).'
  },
  {
    id: 'kula-6',
    name: 'Varahavanshi',
    sanskritName: 'वराहवंशी',
    hindiName: 'वराहवंशी',
    alternativeNames: ['Varahavanshi', 'Boar Dynasty'],
    meaning: 'Boar Dynasty',
    origin: 'Associated with Lord Vishnu\'s Varaha avatar',
    description: 'The Boar Dynasty, associated with the Varaha avatar of Lord Vishnu.'
  },
  {
    id: 'kula-7',
    name: 'Garudavanshi',
    sanskritName: 'गरुडवंशी',
    hindiName: 'गरुडवंशी',
    alternativeNames: ['Garudavanshi', 'Garuda Dynasty'],
    meaning: 'Garuda Dynasty',
    origin: 'Associated with Garuda, the divine eagle',
    description: 'The Garuda Dynasty, associated with Garuda, the mount of Lord Vishnu.'
  },
  {
    id: 'kula-8',
    name: 'Gajavanshi',
    sanskritName: 'गजवंशी',
    hindiName: 'गजवंशी',
    alternativeNames: ['Gajavanshi', 'Elephant Dynasty', 'Hathi Vansh'],
    meaning: 'Elephant Dynasty',
    origin: 'Associated with elephants',
    description: 'The Elephant Dynasty, symbolizing strength and wisdom.'
  },
  {
    id: 'kula-9',
    name: 'Simhavanshi',
    sanskritName: 'सिंहवंशी',
    hindiName: 'सिंहवंशी',
    alternativeNames: ['Simhavanshi', 'Lion Dynasty', 'Sinh Vansh'],
    meaning: 'Lion Dynasty',
    origin: 'Associated with lions',
    description: 'The Lion Dynasty, symbolizing courage and royalty.'
  },
  {
    id: 'kula-10',
    name: 'Vrishni',
    sanskritName: 'वृष्णि',
    hindiName: 'वृष्णि',
    alternativeNames: ['Vrishni', 'Yadava'],
    meaning: 'Yadava Clan',
    origin: 'Descended from Vrishni, ancestor of Lord Krishna',
    description: 'The Vrishni clan, to which Lord Krishna belonged. Part of the Yadava community.'
  },
  {
    id: 'kula-11',
    name: 'Pandava',
    sanskritName: 'पाण्डव',
    hindiName: 'पाण्डव',
    alternativeNames: ['Pandava', 'Kuru'],
    meaning: 'Descendants of Pandu',
    origin: 'Descended from King Pandu',
    description: 'The Pandava lineage, the five brothers from the Mahabharata.'
  },
  {
    id: 'kula-12',
    name: 'Kaurava',
    sanskritName: 'कौरव',
    hindiName: 'कौरव',
    alternativeNames: ['Kaurava', 'Dhritarashtra lineage'],
    meaning: 'Descendants of Kuru',
    origin: 'Descended from King Dhritarashtra',
    description: 'The Kaurava lineage, the hundred sons of Dhritarashtra from the Mahabharata.'
  },
  {
    id: 'kula-13',
    name: 'Raghu',
    sanskritName: 'रघु',
    hindiName: 'रघु',
    alternativeNames: ['Raghuvanshi', 'Raghava', 'Raghukul'],
    meaning: 'Descendants of Raghu',
    origin: 'Sub-branch of Suryavanshi through King Raghu',
    description: 'The Raghu dynasty, a sub-branch of the Solar Dynasty. Lord Rama was a Raghu.'
  },
  {
    id: 'kula-14',
    name: 'Yadu',
    sanskritName: 'यदु',
    hindiName: 'यदु',
    alternativeNames: ['Yadava', 'Yaduvanshi'],
    meaning: 'Descendants of Yadu',
    origin: 'Sub-branch of Chandravanshi through King Yadu',
    description: 'The Yadu dynasty, a sub-branch of the Lunar Dynasty. Lord Krishna was a Yadava.'
  }
];
