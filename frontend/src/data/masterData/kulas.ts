// Master database for Kula (Dynasties)
export interface Kula {
  id: string;
  name: string;
  nameHindi: string;
  nameTamil?: string;
  nameTelugu?: string;
  aliases: string[];
  symbol: string;
  description: string;
  origin: string;
}

export const kulas: Kula[] = [
  { id: '1', name: 'Suryavanshi', nameHindi: 'सूर्यवंशी', nameTamil: 'சூரியவம்சம்', nameTelugu: 'సూర్యవంశం', aliases: ['Suryavamsa', 'Suryavamsi', 'Solar Dynasty', 'Suryakula'], symbol: 'Sun', description: 'Descended from Surya (Sun God), includes Lord Rama', origin: 'Solar Dynasty' },
  { id: '2', name: 'Chandravanshi', nameHindi: 'चंद्रवंशी', nameTamil: 'சந்திரவம்சம்', nameTelugu: 'చంద్రవంశం', aliases: ['Chandravamsa', 'Chandravamsi', 'Lunar Dynasty', 'Somavanshi'], symbol: 'Moon', description: 'Descended from Chandra (Moon God), includes Lord Krishna', origin: 'Lunar Dynasty' },
  { id: '3', name: 'Agnivanshi', nameHindi: 'अग्निवंशी', nameTamil: 'அக்னிவம்சம்', nameTelugu: 'అగ్నివంశం', aliases: ['Agnivamsa', 'Agnivamsi', 'Fire Dynasty'], symbol: 'Fire', description: 'Descended from Agni (Fire God), primarily Rajput clans', origin: 'Fire Dynasty' },
  { id: '4', name: 'Nagavanshi', nameHindi: 'नागवंशी', nameTamil: 'நாகவம்சம்', nameTelugu: 'నాగవంశం', aliases: ['Nagavamsa', 'Nagavamsi', 'Serpent Dynasty'], symbol: 'Serpent', description: 'Descended from Nagas (Serpent beings), common in Northeast India', origin: 'Serpent Dynasty' },
  { id: '5', name: 'Somavanshi', nameHindi: 'सोमवंशी', nameTamil: 'சோமவம்சம்', nameTelugu: 'సోమవంశం', aliases: ['Somavamsa', 'Somavamsi'], symbol: 'Moon (Soma)', description: 'Another name for Chandravanshi, descended from Soma', origin: 'Lunar Dynasty' },
  { id: '6', name: 'Aryavanshi', nameHindi: 'आर्यवंशी', nameTamil: 'ஆர்யவம்சம்', nameTelugu: 'ఆర్యవంశం', aliases: ['Aryavamsa', 'Aryavamsi', 'Noble Dynasty'], symbol: 'Noble Symbol', description: 'Noble lineage, claimed by various communities', origin: 'Noble Dynasty' },
  { id: '7', name: 'Ikshvaku', nameHindi: 'इक्ष्वाकु', nameTamil: 'இக்ஷ்வாகு', nameTelugu: 'ఇక్ష్వాకు', aliases: ['Ikshvaku', 'Ikshvaku Vansh'], symbol: 'Sugarcane', description: 'Ancient dynasty, Lord Rama belonged to this lineage', origin: 'Solar Dynasty' },
  { id: '8', name: 'Yaduvanshi', nameHindi: 'यादववंशी', nameTamil: 'யாதவவம்சம்', nameTelugu: 'యాదవవంశం', aliases: ['Yaduvamsa', 'Yaduvamsi', 'Yadava Dynasty'], symbol: 'Lotus', description: 'Descended from Yadu, Lord Krishna\'s lineage', origin: 'Lunar Dynasty' }
];

export function searchKulas(query: string): Kula[] {
  if (!query) return [];
  const q = query.toLowerCase().trim();
  return kulas.filter(k =>
    k.name.toLowerCase().includes(q) ||
    k.nameHindi.includes(q) ||
    (k.nameTamil && k.nameTamil.includes(q)) ||
    (k.nameTelugu && k.nameTelugu.includes(q)) ||
    k.aliases.some(alias => alias.toLowerCase().includes(q)) ||
    k.symbol.toLowerCase().includes(q) ||
    k.description.toLowerCase().includes(q)
  );
}
