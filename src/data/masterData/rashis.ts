// Master database for Rashi (12 Zodiac Signs)
export interface Rashi {
  id: string;
  name: string;
  nameHindi: string;
  nameEnglish: string; // Western name
  nameTamil?: string;
  nameTelugu?: string;
  symbol: string;
  element: string; // Fire, Earth, Air, Water
  lord: string; // Ruling planet
  nakshatras: string[]; // Nakshatras in this rashi
}

export const rashis: Rashi[] = [
  { id: '1', name: 'Mesha', nameHindi: 'मेष', nameEnglish: 'Aries', nameTamil: 'மேஷம்', nameTelugu: 'మేషం', symbol: 'Ram', element: 'Fire', lord: 'Mars', nakshatras: ['Ashwini', 'Bharani', 'Krittika (1st quarter)'] },
  { id: '2', name: 'Vrishabha', nameHindi: 'वृषभ', nameEnglish: 'Taurus', nameTamil: 'ரிஷபம்', nameTelugu: 'వృషభం', symbol: 'Bull', element: 'Earth', lord: 'Venus', nakshatras: ['Krittika (2-4)', 'Rohini', 'Mrigashira (1-2)'] },
  { id: '3', name: 'Mithuna', nameHindi: 'मिथुन', nameEnglish: 'Gemini', nameTamil: 'மிதுனம்', nameTelugu: 'మిథునం', symbol: 'Twins', element: 'Air', lord: 'Mercury', nakshatras: ['Mrigashira (3-4)', 'Ardra', 'Punarvasu (1-3)'] },
  { id: '4', name: 'Karka', nameHindi: 'कर्क', nameEnglish: 'Cancer', nameTamil: 'கடகம்', nameTelugu: 'కర్కాటకం', symbol: 'Crab', element: 'Water', lord: 'Moon', nakshatras: ['Punarvasu (4th)', 'Pushya', 'Ashlesha'] },
  { id: '5', name: 'Simha', nameHindi: 'सिंह', nameEnglish: 'Leo', nameTamil: 'சிம்மம்', nameTelugu: 'సింహం', symbol: 'Lion', element: 'Fire', lord: 'Sun', nakshatras: ['Magha', 'Purva Phalguni', 'Uttara Phalguni (1st)'] },
  { id: '6', name: 'Kanya', nameHindi: 'कन्या', nameEnglish: 'Virgo', nameTamil: 'கன்னி', nameTelugu: 'కన్య', symbol: 'Virgin', element: 'Earth', lord: 'Mercury', nakshatras: ['Uttara Phalguni (2-4)', 'Hasta', 'Chitra (1-3)'] },
  { id: '7', name: 'Tula', nameHindi: 'तुला', nameEnglish: 'Libra', nameTamil: 'துலாம்', nameTelugu: 'తుల', symbol: 'Scales', element: 'Air', lord: 'Venus', nakshatras: ['Chitra (4th)', 'Swati', 'Vishakha (1-3)'] },
  { id: '8', name: 'Vrischika', nameHindi: 'वृश्चिक', nameEnglish: 'Scorpio', nameTamil: 'விருச்சிகம்', nameTelugu: 'వృశ్చికం', symbol: 'Scorpion', element: 'Water', lord: 'Mars', nakshatras: ['Vishakha (4th)', 'Anuradha', 'Jyeshtha'] },
  { id: '9', name: 'Dhanu', nameHindi: 'धनु', nameEnglish: 'Sagittarius', nameTamil: 'தனுசு', nameTelugu: 'ధనస్సు', symbol: 'Archer/Bow', element: 'Fire', lord: 'Jupiter', nakshatras: ['Mula', 'Purva Ashadha', 'Uttara Ashadha (1st)'] },
  { id: '10', name: 'Makara', nameHindi: 'मकर', nameEnglish: 'Capricorn', nameTamil: 'மகரம்', nameTelugu: 'మకరం', symbol: 'Sea Monster/Crocodile', element: 'Earth', lord: 'Saturn', nakshatras: ['Uttara Ashadha (2-4)', 'Shravana', 'Dhanishta (1-2)'] },
  { id: '11', name: 'Kumbha', nameHindi: 'कुम्भ', nameEnglish: 'Aquarius', nameTamil: 'கும்பம்', nameTelugu: 'కుంభం', symbol: 'Water Bearer', element: 'Air', lord: 'Saturn/Rahu', nakshatras: ['Dhanishta (3-4)', 'Shatabhisha', 'Purva Bhadrapada (1-3)'] },
  { id: '12', name: 'Meena', nameHindi: 'मीन', nameEnglish: 'Pisces', nameTamil: 'மீனம்', nameTelugu: 'మీనం', symbol: 'Fish', element: 'Water', lord: 'Jupiter', nakshatras: ['Purva Bhadrapada (4th)', 'Uttara Bhadrapada', 'Revati'] }
];

export function searchRashis(query: string): Rashi[] {
  if (!query) return [];
  const q = query.toLowerCase().trim();
  return rashis.filter(r =>
    r.name.toLowerCase().includes(q) ||
    r.nameHindi.includes(q) ||
    r.nameEnglish.toLowerCase().includes(q) ||
    (r.nameTamil && r.nameTamil.includes(q)) ||
    (r.nameTelugu && r.nameTelugu.includes(q)) ||
    r.symbol.toLowerCase().includes(q) ||
    r.element.toLowerCase().includes(q) ||
    r.lord.toLowerCase().includes(q)
  );
}
