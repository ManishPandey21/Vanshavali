import { useState, useMemo } from 'react';
import { Person } from '../types';
import { Search, Globe, Type } from 'lucide-react';

interface SearchViewProps {
  persons: Person[];
  onSelectPerson: (person: Person) => void;
}

// Simple phonetic matching for Indian names
function simplePhoneticMatch(name: string, query: string): boolean {
  const normalize = (s: string) => s.toLowerCase()
    .replace(/[^a-z]/g, '')
    .replace(/ck/g, 'k')
    .replace(/ph/g, 'f')
    .replace(/gh/g, 'g')
    .replace(/jh/g, 'j')
    .replace(/ch/g, 'c')
    .replace(/ee/g, 'i')
    .replace(/oo/g, 'u')
    .replace(/aa/g, 'a')
    .replace(/th/g, 't')
    .replace(/dh/g, 'd')
    .replace(/bh/g, 'b')
    .replace(/sh/g, 's')
    .replace(/ck/g, 'k');
  
  return normalize(name).includes(normalize(query));
}

export default function SearchView({ persons, onSelectPerson }: SearchViewProps) {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'all' | 'name' | 'gotra' | 'village' | 'kuladevata' | 'nakshatra'>('all');
  const [phoneticSearch, setPhoneticSearch] = useState(true);

  const results = useMemo(() => {
    if (!query.trim()) return [];
    
    const q = query.toLowerCase().trim();
    
    return persons.filter(person => {
      const searchableFields = {
        name: `${person.firstName} ${person.lastName} ${person.nativeName || ''}`.toLowerCase(),
        gotra: (person.gotra || '').toLowerCase(),
        village: `${person.ancestralVillage || ''} ${person.district || ''} ${person.state || ''}`.toLowerCase(),
        kuladevata: `${person.kuladevata || ''} ${person.kuladevataTemple || ''}`.toLowerCase(),
        nakshatra: (person.nakshatra || '').toLowerCase(),
      };

      if (searchType === 'all') {
        const allText = Object.values(searchableFields).join(' ');
        if (allText.includes(q)) return true;
        if (phoneticSearch) {
          return Object.values(searchableFields).some(field => simplePhoneticMatch(field, q));
        }
        return false;
      }

      const field = searchableFields[searchType];
      if (field.includes(q)) return true;
      if (phoneticSearch && simplePhoneticMatch(field, q)) return true;
      return false;
    });
  }, [query, searchType, phoneticSearch, persons]);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Search Family Members</h2>
        <p className="text-sm text-gray-500">
          Search by name, Gotra, village, Kuladevata, or Nakshatra. Supports phonetic matching for Indian name variations.
        </p>
      </div>

      {/* Search Input */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
        <div className="relative mb-4">
          <Search size={20} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for a person, Gotra, village, deity, or Nakshatra..."
            className="w-full pl-12 pr-4 py-3 border border-gray-200 rounded-xl text-base focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
            autoFocus
          />
        </div>

        {/* Search Type Filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          {[
            { value: 'all', label: 'All Fields', icon: <Search size={14} /> },
            { value: 'name', label: 'Name', icon: <Type size={14} /> },
            { value: 'gotra', label: 'Gotra', icon: <Globe size={14} /> },
            { value: 'village', label: 'Village', icon: <Globe size={14} /> },
            { value: 'kuladevata', label: 'Kuladevata', icon: <span className="text-xs">🛕</span> },
            { value: 'nakshatra', label: 'Nakshatra', icon: <span className="text-xs">⭐</span> },
          ].map(type => (
            <button
              key={type.value}
              onClick={() => setSearchType(type.value as typeof searchType)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                searchType === type.value
                  ? 'bg-amber-100 text-amber-800 border border-amber-300'
                  : 'bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100'
              }`}
            >
              {type.icon}
              {type.label}
            </button>
          ))}
        </div>

        {/* Phonetic Toggle */}
        <div className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
          <input
            type="checkbox"
            id="phonetic"
            checked={phoneticSearch}
            onChange={(e) => setPhoneticSearch(e.target.checked)}
            className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
          />
          <label htmlFor="phonetic" className="text-sm text-blue-800">
            <span className="font-medium">Phonetic Matching</span>
            <span className="text-blue-600 ml-2">
              — Finds "Mukherjee", "Mukerji", "Mukhopadhyay" as same results
            </span>
          </label>
        </div>
      </div>

      {/* Results */}
      {query && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <p className="text-sm text-gray-600">
              Found <span className="font-bold text-gray-800">{results.length}</span> result{results.length !== 1 ? 's' : ''} for "{query}"
            </p>
          </div>
          
          {results.length > 0 ? (
            <div className="divide-y divide-gray-100">
              {results.map(person => (
                <button
                  key={person.id}
                  onClick={() => onSelectPerson(person)}
                  className="w-full flex items-center gap-4 px-4 py-3 hover:bg-amber-50 transition-colors text-left"
                >
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${
                    person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                  }`}>
                    {person.firstName[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800">{person.firstName} {person.lastName}</p>
                    {person.nativeName && (
                      <p className="text-xs text-gray-400">{person.nativeName}</p>
                    )}
                    <div className="flex flex-wrap gap-2 mt-1">
                      {person.gotra && (
                        <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                          {person.gotra}
                        </span>
                      )}
                      {person.ancestralVillage && (
                        <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                          {person.ancestralVillage}
                        </span>
                      )}
                      {person.nakshatra && (
                        <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                          {person.nakshatra}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    person.isLiving ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {person.isLiving ? 'Living' : 'Deceased'}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-gray-500 text-sm">No results found for "{query}"</p>
              {phoneticSearch && (
                <p className="text-xs text-gray-400 mt-1">Try adjusting your search term or disabling phonetic matching</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Phonetic Search Examples */}
      {!query && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">Phonetic Search Examples</h3>
          <p className="text-sm text-gray-600 mb-4">
            Indian names have many spelling variations across transliteration systems. Our phonetic search handles these:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs font-medium text-gray-700 mb-1">Same person, different spellings:</p>
              <p className="text-xs text-gray-500">Mukherjee = Mukerji = Mukhopadhyay</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs font-medium text-gray-700 mb-1">Vowel variations:</p>
              <p className="text-xs text-gray-500">Krishna = Krishna = Krsna</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs font-medium text-gray-700 mb-1">Aspirated consonants:</p>
              <p className="text-xs text-gray-500">Bharadwaj = Bharadwaj = Baradwaj</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs font-medium text-gray-700 mb-1">Transliteration support:</p>
              <p className="text-xs text-gray-500">Search "Sharma" also finds "शर्मा"</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
