import { useState } from 'react';
import { Person } from '../types';
import { Search, Filter, UserPlus, ChevronDown } from 'lucide-react';

interface MemberListProps {
  persons: Person[];
  onSelectPerson: (person: Person) => void;
  onAddPerson: () => void;
}

export default function MemberList({ persons, onSelectPerson, onAddPerson }: MemberListProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterGender, setFilterGender] = useState<string>('all');
  const [filterLiving, setFilterLiving] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('name');

  const filteredPersons = persons
    .filter(p => {
      const matchesSearch = `${p.firstName} ${p.lastName} ${p.gotra} ${p.ancestralVillage} ${p.nativeName || ''}`
        .toLowerCase()
        .includes(searchTerm.toLowerCase());
      const matchesGender = filterGender === 'all' || p.gender === filterGender;
      const matchesLiving = filterLiving === 'all' || 
        (filterLiving === 'living' && p.isLiving) || 
        (filterLiving === 'deceased' && !p.isLiving);
      return matchesSearch && matchesGender && matchesLiving;
    })
    .sort((a, b) => {
      if (sortBy === 'name') return `${a.firstName} ${a.lastName}`.localeCompare(`${b.firstName} ${b.lastName}`);
      if (sortBy === 'birth') return (a.birthDate || '').localeCompare(b.birthDate || '');
      if (sortBy === 'gotra') return (a.gotra || '').localeCompare(b.gotra || '');
      return 0;
    });

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Family Members</h2>
          <p className="text-sm text-gray-500">{persons.length} members in the family tree</p>
        </div>
        <button
          onClick={onAddPerson}
          className="flex items-center gap-2 bg-amber-700 text-white px-4 py-2 rounded-lg hover:bg-amber-800 transition-colors shadow-sm"
        >
          <UserPlus size={18} />
          <span className="text-sm font-medium">Add Member</span>
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm">
        <div className="flex flex-wrap gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[200px] relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search by name, gotra, village, or native script..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
            />
          </div>

          {/* Gender Filter */}
          <div className="relative">
            <select
              value={filterGender}
              onChange={(e) => setFilterGender(e.target.value)}
              className="appearance-none bg-gray-50 border border-gray-200 rounded-lg px-4 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="all">All Genders</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>

          {/* Living Status */}
          <div className="relative">
            <select
              value={filterLiving}
              onChange={(e) => setFilterLiving(e.target.value)}
              className="appearance-none bg-gray-50 border border-gray-200 rounded-lg px-4 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="all">All Status</option>
              <option value="living">Living</option>
              <option value="deceased">Deceased</option>
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>

          {/* Sort */}
          <div className="relative">
            <Filter size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="appearance-none bg-gray-50 border border-gray-200 rounded-lg pl-7 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="name">Sort by Name</option>
              <option value="birth">Sort by Birth</option>
              <option value="gotra">Sort by Gotra</option>
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Gotra</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Village</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Nakshatra</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Privacy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredPersons.map(person => (
                <tr
                  key={person.id}
                  onClick={() => onSelectPerson(person)}
                  className="hover:bg-amber-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                        person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                      }`}>
                        {person.firstName[0]}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">{person.firstName} {person.lastName}</p>
                        {person.nativeName && (
                          <p className="text-xs text-gray-400">{person.nativeName}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-700">{person.gotra || '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-700">{person.ancestralVillage || '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-700">{person.nakshatra || '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full ${
                      person.isLiving ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${person.isLiving ? 'bg-green-500' : 'bg-gray-400'}`}></span>
                      {person.isLiving ? 'Living' : 'Deceased'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {person.isPrivate ? (
                      <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded-full">🔒 Private</span>
                    ) : (
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">🌐 Public</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filteredPersons.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-sm">No members found matching your criteria.</p>
          </div>
        )}
      </div>
    </div>
  );
}
