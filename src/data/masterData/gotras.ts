// Master data for Gotras (Lineage/Clan systems)
export interface Gotra {
  id: string;
  name: string;
  sanskritName: string;
  hindiName: string;
  alternativeNames: string[];
  rishi: string; // Founding sage
  pravara?: string; // Sacred lineage
  description?: string;
}

export const gotras: Gotra[] = [
  {
    id: 'gotra-1',
    name: 'Kashyapa',
    sanskritName: 'काश्यप',
    hindiName: 'काश्यप',
    alternativeNames: ['Kashyap', 'Kashyapa', 'Kasyapa'],
    rishi: 'Kashyapa Rishi',
    pravara: 'Kashyapa, Aghamarshana, Naidhruva',
    description: 'One of the most common gotras, descended from sage Kashyapa'
  },
  {
    id: 'gotra-2',
    name: 'Bharadwaj',
    sanskritName: 'भारद्वाज',
    hindiName: 'भारद्वाज',
    alternativeNames: ['Bharadwaj', 'Bhardwaj', 'Bharadwaja'],
    rishi: 'Bharadwaj Rishi',
    pravara: 'Angirasa, Bharhaspatya, Bharadwaja',
    description: 'Descended from sage Bharadwaj, one of the Saptarishis'
  },
  {
    id: 'gotra-3',
    name: 'Vashishtha',
    sanskritName: 'वशिष्ठ',
    hindiName: 'वशिष्ठ',
    alternativeNames: ['Vashishtha', 'Vasishtha', 'Vasishta'],
    rishi: 'Vashishtha Rishi',
    pravara: 'Vashishtha, Indra, Prajapati',
    description: 'Descended from sage Vashishtha, family priest of Lord Rama'
  },
  {
    id: 'gotra-4',
    name: 'Atri',
    sanskritName: 'अत्रि',
    hindiName: 'अत्रि',
    alternativeNames: ['Atri'],
    rishi: 'Atri Rishi',
    pravara: 'Atri, Arcananas, Avalokan',
    description: 'One of the Saptarishis, descended from sage Atri'
  },
  {
    id: 'gotra-5',
    name: 'Angirasa',
    sanskritName: 'आंगिरस',
    hindiName: 'आंगिरस',
    alternativeNames: ['Angirasa', 'Angiras', 'Angirasa'],
    rishi: 'Angirasa Rishi',
    pravara: 'Angirasa, Utathya, Samvartana',
    description: 'Descended from sage Angirasa'
  },
  {
    id: 'gotra-6',
    name: 'Bhargava',
    sanskritName: 'भार्गव',
    hindiName: 'भार्गव',
    alternativeNames: ['Bhargava', 'Bhargav'],
    rishi: 'Bhrigu Rishi',
    pravara: 'Bhargava, Chyavana, Apnavan',
    description: 'Descended from sage Bhrigu'
  },
  {
    id: 'gotra-7',
    name: 'Agastya',
    sanskritName: 'अगस्त्य',
    hindiName: 'अगस्त्य',
    alternativeNames: ['Agastya', 'Agasthya', 'Agasti'],
    rishi: 'Agastya Rishi',
    pravara: 'Agastya, Saubhari, Aila',
    description: 'Descended from sage Agastya, prominent in South India'
  },
  {
    id: 'gotra-8',
    name: 'Gautama',
    sanskritName: 'गौतम',
    hindiName: 'गौतम',
    alternativeNames: ['Gautama', 'Gotama', 'Gautam'],
    rishi: 'Gautama Rishi',
    pravara: 'Angirasa, Ayasasya, Gautama',
    description: 'Descended from sage Gautama'
  },
  {
    id: 'gotra-9',
    name: 'Jamadagni',
    sanskritName: 'जमदग्नि',
    hindiName: 'जमदग्नि',
    alternativeNames: ['Jamadagni', 'Jamadagnya'],
    rishi: 'Jamadagni Rishi',
    pravara: 'Bhargava, Chyavana, Apnavan, Aurva, Jamadagnya',
    description: 'Descended from sage Jamadagni, father of Parashurama'
  },
  {
    id: 'gotra-10',
    name: 'Vishwamitra',
    sanskritName: 'विश्वामित्र',
    hindiName: 'विश्वामित्र',
    alternativeNames: ['Vishwamitra', 'Vishvamitra', 'Vishva Mitra'],
    rishi: 'Vishwamitra Rishi',
    pravara: 'Vishwamitra, Devarata, Audalomi',
    description: 'Descended from sage Vishwamitra'
  },
  {
    id: 'gotra-11',
    name: 'Shandilya',
    sanskritName: 'शाण्डिल्य',
    hindiName: 'शाण्डिल्य',
    alternativeNames: ['Shandilya', 'Sandilya', 'Shandilya'],
    rishi: 'Shandilya Rishi',
    pravara: 'Shandilya, Aghamarshana, Devala',
    description: 'Descended from sage Shandilya'
  },
  {
    id: 'gotra-12',
    name: 'Parashara',
    sanskritName: 'पाराशर',
    hindiName: 'पाराशर',
    alternativeNames: ['Parashara', 'Parasar', 'Parashar'],
    rishi: 'Parashara Rishi',
    pravara: 'Vasishtha, Shaktya, Parasharya',
    description: 'Descended from sage Parashara, father of Vyasa'
  },
  {
    id: 'gotra-13',
    name: 'Pulaha',
    sanskritName: 'पुलह',
    hindiName: 'पुलह',
    alternativeNames: ['Pulaha', 'Pulaha'],
    rishi: 'Pulaha Rishi',
    description: 'Descended from sage Pulaha'
  },
  {
    id: 'gotra-14',
    name: 'Pulastya',
    sanskritName: 'पुलस्त्य',
    hindiName: 'पुलस्त्य',
    alternativeNames: ['Pulastya', 'Pulasthya'],
    rishi: 'Pulastya Rishi',
    description: 'Descended from sage Pulastya, grandfather of Ravana'
  },
  {
    id: 'gotra-15',
    name: 'Kratu',
    sanskritName: 'क्रतु',
    hindiName: 'क्रतु',
    alternativeNames: ['Kratu', 'Krathu'],
    rishi: 'Kratu Rishi',
    description: 'Descended from sage Kratu'
  },
  {
    id: 'gotra-16',
    name: 'Pulastya-Vashishtha',
    sanskritName: 'पुलस्त्य-वशिष्ठ',
    hindiName: 'पुलस्त्य-वशिष्ठ',
    alternativeNames: ['Pulastya Vashishtha'],
    rishi: 'Combined lineage',
    description: 'Combined lineage of Pulastya and Vashishtha'
  },
  {
    id: 'gotra-17',
    name: 'Garga',
    sanskritName: 'गर्ग',
    hindiName: 'गर्ग',
    alternativeNames: ['Garga', 'Garg'],
    rishi: 'Garga Rishi',
    pravara: 'Angirasa, Gargya, Bharadvaja',
    description: 'Descended from sage Garga, famous astronomer'
  },
  {
    id: 'gotra-18',
    name: 'Kaushika',
    sanskritName: 'कौशिक',
    hindiName: 'कौशिक',
    alternativeNames: ['Kaushika', 'Koushika', 'Kaushik'],
    rishi: 'Vishwamitra (Kaushika)',
    description: 'Alternative name for Vishwamitra gotra'
  },
  {
    id: 'gotra-19',
    name: 'Maudgalya',
    sanskritName: 'मौद्गल्य',
    hindiName: 'मौद्गल्य',
    alternativeNames: ['Maudgalya', 'Mudgala', 'Mudgalya'],
    rishi: 'Mudgala Rishi',
    description: 'Descended from sage Mudgala'
  },
  {
    id: 'gotra-20',
    name: 'Kapila',
    sanskritName: 'कपिल',
    hindiName: 'कपिल',
    alternativeNames: ['Kapila', 'Kapil'],
    rishi: 'Kapila Rishi',
    description: 'Descended from sage Kapila, founder of Samkhya philosophy'
  },
  {
    id: 'gotra-21',
    name: 'Upamanyu',
    sanskritName: 'उपमन्यु',
    hindiName: 'उपमन्यु',
    alternativeNames: ['Upamanyu', 'Upamanyava'],
    rishi: 'Upamanyu Rishi',
    description: 'Descended from sage Upamanyu'
  },
  {
    id: 'gotra-22',
    name: 'Kutsa',
    sanskritName: 'कुत्स',
    hindiName: 'कुत्स',
    alternativeNames: ['Kutsa', 'Kuts'],
    rishi: 'Kutsa Rishi',
    description: 'Descended from sage Kutsa'
  },
  {
    id: 'gotra-23',
    name: 'Auddalaka',
    sanskritName: 'औद्दालक',
    hindiName: 'औद्दालक',
    alternativeNames: ['Auddalaka', 'Uddalaka', 'Aruni'],
    rishi: 'Uddalaka Aruni',
    description: 'Descended from sage Uddalaka Aruni'
  },
  {
    id: 'gotra-24',
    name: 'Vatapi',
    sanskritName: 'वटापि',
    hindiName: 'वटापि',
    alternativeNames: ['Vatapi', 'Vadapi'],
    rishi: 'Vatapi Rishi',
    description: 'Descended from sage Vatapi'
  },
  {
    id: 'gotra-25',
    name: 'Kanva',
    sanskritName: 'कण्व',
    hindiName: 'कण्व',
    alternativeNames: ['Kanva', 'Kanva'],
    rishi: 'Kanva Rishi',
    description: 'Descended from sage Kanva, foster father of Shakuntala'
  }
];
