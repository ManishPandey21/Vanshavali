import { useState } from 'react';
import { Person } from '../types';
import { AlertTriangle, CheckCircle, MapPin, Users } from 'lucide-react';

interface GotraViewProps {
  persons: Person[];
}

export default function GotraView({ persons }: GotraViewProps) {
  const [selectedPerson1, setSelectedPerson1] = useState<string>('');
  const [selectedPerson2, setSelectedPerson2] = useState<string>('');

  const person1 = persons.find(p => p.id === selectedPerson1);
  const person2 = persons.find(p => p.id === selectedPerson2);

  // Gotra compatibility check
  const isSameGotra = person1 && person2 && person1.gotra === person2.gotra;
  const isCompatible = person1 && person2 && !isSameGotra;

  // Group by Gotra
  const gotraGroups = persons.reduce((acc, person) => {
    const gotra = person.gotra || 'Unknown';
    if (!acc[gotra]) acc[gotra] = [];
    acc[gotra].push(person);
    return acc;
  }, {} as Record<string, Person[]>);

  // Group by Kuladevata
  const kuladevataGroups = persons.reduce((acc, person) => {
    const devata = person.kuladevata || 'Unknown';
    if (!acc[devata]) acc[devata] = [];
    acc[devata].push(person);
    return acc;
  }, {} as Record<string, Person[]>);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Gotra & Kuladevata</h2>
        <p className="text-sm text-gray-500">
          Check Gotra compatibility for matrimonial purposes and explore family deity connections
        </p>
      </div>

      {/* Gotra Matching Tool */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-8">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <AlertTriangle size={18} className="text-amber-600" />
          Gotra Compatibility Check (Sagotra Marriage Prevention)
        </h3>
        <p className="text-sm text-gray-600 mb-4">
          In Hindu tradition, marriage between persons of the same Gotra (Sagotra) is prohibited. 
          Select two individuals to check compatibility.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Person 1 (Prospective Bride/Groom)</label>
            <select
              value={selectedPerson1}
              onChange={(e) => setSelectedPerson1(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="">Select Person</option>
              {persons.filter(p => p.isLiving && !p.isPrivate).map(p => (
                <option key={p.id} value={p.id}>
                  {p.firstName} {p.lastName} ({p.gotra || 'No Gotra'})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Person 2 (Prospective Bride/Groom)</label>
            <select
              value={selectedPerson2}
              onChange={(e) => setSelectedPerson2(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="">Select Person</option>
              {persons.filter(p => p.isLiving && !p.isPrivate && p.id !== selectedPerson1).map(p => (
                <option key={p.id} value={p.id}>
                  {p.firstName} {p.lastName} ({p.gotra || 'No Gotra'})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Result */}
        {person1 && person2 && (
          <div className={`p-4 rounded-lg border ${
            isCompatible 
              ? 'bg-green-50 border-green-200' 
              : 'bg-red-50 border-red-200'
          }`}>
            {isCompatible ? (
              <div className="flex items-start gap-3">
                <CheckCircle size={20} className="text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-green-800">✓ Compatible for Marriage</p>
                  <p className="text-sm text-green-700 mt-1">
                    {person1.firstName}'s Gotra ({person1.gotra}) is different from {person2.firstName}'s Gotra ({person2.gotra}). 
                    This marriage is acceptable as per Gotra exogamy rules.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="text-red-600 mt-0.5" />
                <div>
                  <p className="font-medium text-red-800">✗ Not Compatible - Same Gotra (Sagotra)</p>
                  <p className="text-sm text-red-700 mt-1">
                    Both {person1.firstName} and {person2.firstName} belong to the <strong>{person1.gotra}</strong> Gotra. 
                    According to Hindu tradition, Sagotra (same-clan) marriage is prohibited as they are considered siblings.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Gotra Distribution */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-8">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Users size={18} className="text-blue-600" />
          Gotra Distribution in Family
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(gotraGroups).sort((a, b) => b[1].length - a[1].length).map(([gotra, members]) => (
            <div key={gotra} className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-gray-800">{gotra}</h4>
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                  {members.length} members
                </span>
              </div>
              <div className="space-y-1">
                {members.slice(0, 4).map(m => (
                  <p key={m.id} className="text-xs text-gray-600 truncate">
                    {m.firstName} {m.lastName}
                  </p>
                ))}
                {members.length > 4 && (
                  <p className="text-xs text-gray-400">+{members.length - 4} more...</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Kuladevata Mapping */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <MapPin size={18} className="text-purple-600" />
          Kuladevata (Family Deity) Mapping
        </h3>
        <p className="text-sm text-gray-600 mb-4">
          The Kuladevata is the family's patron deity. Families sharing the same Kuladevata often have historical connections.
          This mapping helps discover shared ancestry with strangers who worship the same deity.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(kuladevataGroups).sort((a, b) => b[1].length - a[1].length).map(([devata, members]) => {
            const temples = [...new Set(members.map(m => m.kuladevataTemple).filter(Boolean))];
            return (
              <div key={devata} className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-lg p-4 border border-amber-100">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🛕</span>
                  <div>
                    <h4 className="font-medium text-amber-900">{devata}</h4>
                    <p className="text-xs text-amber-700">{members.length} families worship this deity</p>
                  </div>
                </div>
                {temples.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {temples.map((temple, idx) => (
                      <p key={idx} className="text-xs text-gray-600 flex items-center gap-1">
                        <MapPin size={10} className="text-gray-400" />
                        {temple}
                      </p>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-1">
                  {members.slice(0, 5).map(m => (
                    <span key={m.id} className="text-[10px] bg-white/80 text-gray-700 px-1.5 py-0.5 rounded border border-amber-200">
                      {m.lastName}
                    </span>
                  ))}
                  {members.length > 5 && (
                    <span className="text-[10px] text-gray-500">+{members.length - 5} more</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
