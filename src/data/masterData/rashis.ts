// Master data for Rashis (12 Zodiac Signs)
export interface Rashi {
  id: string;
  name: string;
  sanskritName: string;
  hindiName: string;
  englishName: string;
  alternativeNames: string[];
  element: string;
  lord: string;
  symbol: string;
}

export const rashis: Rashi[] = [
  {
    id: 'rashi-1',
    name: 'Mesha',
    sanskritName: 'मेष',
    hindiName: 'मेष',
    englishName: 'Aries',
    alternativeNames: ['Mesha', 'Mesh'],
    element: 'Fire',
    lord: 'Mars',
    symbol: 'Ram'
  },
  {
    id: 'rashi-2',
    name: 'Vrishabha',
    sanskritName: 'वृषभ',
    hindiName: 'वृषभ',
    englishName: 'Taurus',
    alternativeNames: ['Vrishabha', 'Rishabha', 'Rishabh'],
    element: 'Earth',
    lord: 'Venus',
    symbol: 'Bull'
  },
  {
    id: 'rashi-3',
    name: 'Mithuna',
    sanskritName: 'मिथुन',
    hindiName: 'मिथुन',
    englishName: 'Gemini',
    alternativeNames: ['Mithuna', 'Mithun'],
    element: 'Air',
    lord: 'Mercury',
    symbol: 'Twins'
  },
  {
    id: 'rashi-4',
    name: 'Karka',
    sanskritName: 'कर्क',
    hindiName: 'कर्क',
    englishName: 'Cancer',
    alternativeNames: ['Karka', 'Kark', 'Karkataka'],
    element: 'Water',
    lord: 'Moon',
    symbol: 'Crab'
  },
  {
    id: 'rashi-5',
    name: 'Simha',
    sanskritName: 'सिंह',
    hindiName: 'सिंह',
    englishName: 'Leo',
    alternativeNames: ['Simha', 'Singh', 'Sinh'],
    element: 'Fire',
    lord: 'Sun',
    symbol: 'Lion'
  },
  {
    id: 'rashi-6',
    name: 'Kanya',
    sanskritName: 'कन्या',
    hindiName: 'कन्या',
    englishName: 'Virgo',
    alternativeNames: ['Kanya', 'Kanya'],
    element: 'Earth',
    lord: 'Mercury',
    symbol: 'Virgin'
  },
  {
    id: 'rashi-7',
    name: 'Tula',
    sanskritName: 'तुला',
    hindiName: 'तुला',
    englishName: 'Libra',
    alternativeNames: ['Tula', 'Thula'],
    element: 'Air',
    lord: 'Venus',
    symbol: 'Scales'
  },
  {
    id: 'rashi-8',
    name: 'Vrischika',
    sanskritName: 'वृश्चिक',
    hindiName: 'वृश्चिक',
    englishName: 'Scorpio',
    alternativeNames: ['Vrischika', 'Vrishchika', 'Vrichika'],
    element: 'Water',
    lord: 'Mars',
    symbol: 'Scorpion'
  },
  {
    id: 'rashi-9',
    name: 'Dhanu',
    sanskritName: 'धनु',
    hindiName: 'धनु',
    englishName: 'Sagittarius',
    alternativeNames: ['Dhanu', 'Dhanush', 'Dhanus'],
    element: 'Fire',
    lord: 'Jupiter',
    symbol: 'Archer'
  },
  {
    id: 'rashi-10',
    name: 'Makara',
    sanskritName: 'मकर',
    hindiName: 'मकर',
    englishName: 'Capricorn',
    alternativeNames: ['Makara', 'Makar'],
    element: 'Earth',
    lord: 'Saturn',
    symbol: 'Sea-goat'
  },
  {
    id: 'rashi-11',
    name: 'Kumbha',
    sanskritName: 'कुम्भ',
    hindiName: 'कुम्भ',
    englishName: 'Aquarius',
    alternativeNames: ['Kumbha', 'Kumbh'],
    element: 'Air',
    lord: 'Saturn',
    symbol: 'Water-bearer'
  },
  {
    id: 'rashi-12',
    name: 'Meena',
    sanskritName: 'मीन',
    hindiName: 'मीन',
    englishName: 'Pisces',
    alternativeNames: ['Meena', 'Meen'],
    element: 'Water',
    lord: 'Jupiter',
    symbol: 'Fish'
  }
];
