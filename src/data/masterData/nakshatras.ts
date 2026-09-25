// Master database for Nakshatra (27 Birth Stars)
export interface Nakshatra {
  id: string;
  name: string;
  nameHindi: string;
  nameTamil?: string;
  nameTelugu?: string;
  lord: string; // Ruling deity/planet
  symbol: string;
  zodiacSign: string; // Which rashi it falls in
  degrees: string; // Starting degree in zodiac
}

export const nakshatras: Nakshatra[] = [
  { id: '1', name: 'Ashwini', nameHindi: 'अश्विनी', nameTamil: 'அசுவனி', nameTelugu: 'అశ్విని', lord: 'Ketu', symbol: 'Horse Head', zodiacSign: 'Mesha', degrees: '0°00\' - 13°20\'' },
  { id: '2', name: 'Bharani', nameHindi: 'भरणी', nameTamil: 'பரணி', nameTelugu: 'భరణి', lord: 'Venus', symbol: 'Yoni', zodiacSign: 'Mesha', degrees: '13°20\' - 26°40\'' },
  { id: '3', name: 'Krittika', nameHindi: 'कृत्तिका', nameTamil: 'கிருத்திகை', nameTelugu: 'కృత్తిక', lord: 'Sun', symbol: 'Knife/Razor', zodiacSign: 'Mesha/Vrishabha', degrees: '26°40\' - 10°00\'' },
  { id: '4', name: 'Rohini', nameHindi: 'रोहिणी', nameTamil: 'ரோகிணி', nameTelugu: 'రోహిణి', lord: 'Moon', symbol: 'Cart/Chariot', zodiacSign: 'Vrishabha', degrees: '10°00\' - 23°20\'' },
  { id: '5', name: 'Mrigashira', nameHindi: 'मृगशिरा', nameTamil: 'மிருகசிரிஷம்', nameTelugu: 'మృగశిర', lord: 'Mars', symbol: 'Deer Head', zodiacSign: 'Vrishabha/Mithuna', degrees: '23°20\' - 6°40\'' },
  { id: '6', name: 'Ardra', nameHindi: 'आर्द्रा', nameTamil: 'திருவாதிரை', nameTelugu: 'ఆర్ద్ర', lord: 'Rahu', symbol: 'Teardrop', zodiacSign: 'Mithuna', degrees: '6°40\' - 20°00\'' },
  { id: '7', name: 'Punarvasu', nameHindi: 'पुनर्वसु', nameTamil: 'புனர்பூசம்', nameTelugu: 'పునర్వసు', lord: 'Jupiter', symbol: 'Bow & Quiver', zodiacSign: 'Mithuna/Karka', degrees: '20°00\' - 3°20\'' },
  { id: '8', name: 'Pushya', nameHindi: 'पुष्य', nameTamil: 'பூசம்', nameTelugu: 'పుష్యమి', lord: 'Saturn', symbol: 'Circle/Flower', zodiacSign: 'Karka', degrees: '3°20\' - 16°40\'' },
  { id: '9', name: 'Ashlesha', nameHindi: 'आश्लेषा', nameTamil: 'ஆயில்யம்', nameTelugu: 'ఆశ్లేష', lord: 'Mercury', symbol: 'Serpent', zodiacSign: 'Karka', degrees: '16°40\' - 30°00\'' },
  { id: '10', name: 'Magha', nameHindi: 'मघा', nameTamil: 'மகம்', nameTelugu: 'మఖ', lord: 'Ketu', symbol: 'Royal Throne', zodiacSign: 'Simha', degrees: '0°00\' - 13°20\'' },
  { id: '11', name: 'Purva Phalguni', nameHindi: 'पूर्व फाल्गुनी', nameTamil: 'பூரம்', nameTelugu: 'పుప్పూర్వ', lord: 'Venus', symbol: 'Front legs of bed', zodiacSign: 'Simha', degrees: '13°20\' - 26°40\'' },
  { id: '12', name: 'Uttara Phalguni', nameHindi: 'उत्तर फाल्गुनी', nameTamil: 'உத்திரம்', nameTelugu: 'ఉత్తరా', lord: 'Sun', symbol: 'Back legs of bed', zodiacSign: 'Simha/Kanya', degrees: '26°40\' - 10°00\'' },
  { id: '13', name: 'Hasta', nameHindi: 'हस्त', nameTamil: 'ஹஸ்தம்', nameTelugu: 'హస్త', lord: 'Moon', symbol: 'Hand/Fist', zodiacSign: 'Kanya', degrees: '10°00\' - 23°20\'' },
  { id: '14', name: 'Chitra', nameHindi: 'चित्रा', nameTamil: 'சித்திரை', nameTelugu: 'చిత్త', lord: 'Mars', symbol: 'Bright Jewel', zodiacSign: 'Kanya/Tula', degrees: '23°20\' - 6°40\'' },
  { id: '15', name: 'Swati', nameHindi: 'स्वाती', nameTamil: 'சுவாதி', nameTelugu: 'స్వాతి', lord: 'Rahu', symbol: 'Coral/Sword', zodiacSign: 'Tula', degrees: '6°40\' - 20°00\'' },
  { id: '16', name: 'Vishakha', nameHindi: 'विशाखा', nameTamil: 'விசாகம்', nameTelugu: 'విశాఖ', lord: 'Jupiter', symbol: 'Triumphal Arch', zodiacSign: 'Tula/Vrischika', degrees: '20°00\' - 3°20\'' },
  { id: '17', name: 'Anuradha', nameHindi: 'अनुराधा', nameTamil: 'அனுஷம்', nameTelugu: 'అనూరాధ', lord: 'Saturn', symbol: 'Lotus', zodiacSign: 'Vrischika', degrees: '3°20\' - 16°40\'' },
  { id: '18', name: 'Jyeshtha', nameHindi: 'ज्येष्ठा', nameTamil: 'கேட்டை', nameTelugu: 'జ్యేష్ఠ', lord: 'Mercury', symbol: 'Earring/Umbrella', zodiacSign: 'Vrischika', degrees: '16°40\' - 30°00\'' },
  { id: '19', name: 'Mula', nameHindi: 'मूल', nameTamil: 'மூலம்', nameTelugu: 'మూల', lord: 'Ketu', symbol: 'Tied Roots', zodiacSign: 'Dhanu', degrees: '0°00\' - 13°20\'' },
  { id: '20', name: 'Purva Ashadha', nameHindi: 'पूर्वाषाढ़ा', nameTamil: 'பூராடம்', nameTelugu: 'పుర్వాషాఢ', lord: 'Venus', symbol: 'Elephant Tusk', zodiacSign: 'Dhanu', degrees: '13°20\' - 26°40\'' },
  { id: '21', name: 'Uttara Ashadha', nameHindi: 'उत्तराषाढ़ा', nameTamil: 'உத்திராடம்', nameTelugu: 'ఉత్తరాషాఢ', lord: 'Sun', symbol: 'Elephant Tusk', zodiacSign: 'Dhanu/Makara', degrees: '26°40\' - 10°00\'' },
  { id: '22', name: 'Shravana', nameHindi: 'श्रवण', nameTamil: 'திருவோணம்', nameTelugu: 'శ్రవణం', lord: 'Moon', symbol: 'Three Footprints', zodiacSign: 'Makara', degrees: '10°00\' - 23°20\'' },
  { id: '23', name: 'Dhanishta', nameHindi: 'धनिष्ठा', nameTamil: 'அவிட்டம்', nameTelugu: 'ధనిష్ఠ', lord: 'Mars', symbol: 'Drum/Flute', zodiacSign: 'Makara/Kumbha', degrees: '23°20\' - 6°40\'' },
  { id: '24', name: 'Shatabhisha', nameHindi: 'शतभिषा', nameTamil: 'சதயம்', nameTelugu: 'శతభిషం', lord: 'Rahu', symbol: 'Empty Circle', zodiacSign: 'Kumbha', degrees: '6°40\' - 20°00\'' },
  { id: '25', name: 'Purva Bhadrapada', nameHindi: 'पूर्वा भाद्रपद', nameTamil: 'பூரட்டாதி', nameTelugu: 'పుర్వాభాద్ర', lord: 'Jupiter', symbol: 'Front of Funeral Cot', zodiacSign: 'Kumbha', degrees: '20°00\' - 3°20\'' },
  { id: '26', name: 'Uttara Bhadrapada', nameHindi: 'उत्तर भाद्रपद', nameTamil: 'உத்திரட்டாதி', nameTelugu: 'ఉత్తరాభాద్ర', lord: 'Saturn', symbol: 'Back of Funeral Cot', zodiacSign: 'Meena', degrees: '3°20\' - 16°40\'' },
  { id: '27', name: 'Revati', nameHindi: 'रेवती', nameTamil: 'ரேவதி', nameTelugu: 'రేవతి', lord: 'Mercury', symbol: 'Fish/Pair of Fish', zodiacSign: 'Meena', degrees: '16°40\' - 30°00\'' }
];

export function searchNakshatras(query: string): Nakshatra[] {
  if (!query) return [];
  const q = query.toLowerCase().trim();
  return nakshatras.filter(n => 
    n.name.toLowerCase().includes(q) ||
    n.nameHindi.includes(q) ||
    (n.nameTamil && n.nameTamil.includes(q)) ||
    (n.nameTelugu && n.nameTelugu.includes(q)) ||
    n.lord.toLowerCase().includes(q) ||
    n.symbol.toLowerCase().includes(q)
  );
}
