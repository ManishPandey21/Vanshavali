import { Person, Family, Household, Page } from '../types';
import { Users, Home, MapPin, TreePine, Star, Heart, TrendingUp } from 'lucide-react';

interface DashboardProps {
  family: Family;
  persons: Person[];
  households: Household[];
  onSelectPerson: (person: Person) => void;
  onNavigate: (page: Page) => void;
}

export default function Dashboard({ family, persons, households, onSelectPerson, onNavigate }: DashboardProps) {
  const livingCount = persons.filter(p => p.isLiving).length;
  const deceasedCount = persons.filter(p => !p.isLiving).length;
  const gotras = [...new Set(persons.map(p => p.gotra).filter(Boolean))];
  const states = [...new Set(persons.map(p => p.state).filter(Boolean))];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-amber-800 via-amber-700 to-orange-700 rounded-2xl p-8 mb-8 text-white shadow-xl relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <svg viewBox="0 0 400 400" className="w-full h-full">
            <pattern id="mandala" x="0" y="0" width="100" height="100" patternUnits="userSpaceOnUse">
              <circle cx="50" cy="50" r="40" fill="none" stroke="white" strokeWidth="0.5" />
              <circle cx="50" cy="50" r="30" fill="none" stroke="white" strokeWidth="0.5" />
              <circle cx="50" cy="50" r="20" fill="none" stroke="white" strokeWidth="0.5" />
              <circle cx="50" cy="50" r="10" fill="none" stroke="white" strokeWidth="0.5" />
            </pattern>
            <rect width="400" height="400" fill="url(#mandala)" />
          </svg>
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-2">
            <TreePine size={24} />
            <span className="text-amber-200 text-sm font-medium">वंशावली</span>
          </div>
          <h1 className="text-3xl font-bold mb-2">{family.name} Family Tree</h1>
          <p className="text-amber-200 mb-4">
            {family.gotra} Gotra • {family.kula} • {family.kuladevata}
          </p>
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="bg-white/10 px-3 py-1 rounded-full">
              🏠 Ancestral: {family.ancestralVillage}, {family.state}
            </span>
            <span className="bg-white/10 px-3 py-1 rounded-full">
              🛕 Kuladevata: {family.kuladevataTemple}
            </span>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={<Users size={24} className="text-blue-600" />}
          label="Total Members"
          value={persons.length}
          sublabel={`${livingCount} living, ${deceasedCount} deceased`}
          color="blue"
        />
        <StatCard
          icon={<Home size={24} className="text-green-600" />}
          label="Households"
          value={households.length}
          sublabel="Across multiple cities"
          color="green"
        />
        <StatCard
          icon={<MapPin size={24} className="text-purple-600" />}
          label="States Connected"
          value={states.length}
          sublabel={states.join(', ')}
          color="purple"
        />
        <StatCard
          icon={<Star size={24} className="text-amber-600" />}
          label="Gotras"
          value={gotras.length}
          sublabel={gotras.join(', ')}
          color="amber"
        />
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
              <TreePine size={20} className="text-amber-700" />
            </div>
            <h3 className="font-semibold text-gray-800">Explore Family Tree</h3>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            View the complete family tree in cluster mode, showing all households and their connections.
          </p>
          <button
            onClick={() => onNavigate('tree')}
            className="w-full bg-amber-700 text-white py-2 rounded-lg hover:bg-amber-800 transition-colors text-sm font-medium"
          >
            View Tree →
          </button>
        </div>

        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <Heart size={20} className="text-purple-700" />
            </div>
            <h3 className="font-semibold text-gray-800">Gotra Matching</h3>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Check Gotra compatibility for matrimonial purposes. Ensure exogamy rules are followed.
          </p>
          <button
            onClick={() => onNavigate('gotra')}
            className="w-full bg-purple-700 text-white py-2 rounded-lg hover:bg-purple-800 transition-colors text-sm font-medium"
          >
            Check Gotra →
          </button>
        </div>

        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <TrendingUp size={20} className="text-green-700" />
            </div>
            <h3 className="font-semibold text-gray-800">Generate Biodata</h3>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Create traditional Indian matrimonial biodata from family tree data. Export as PDF.
          </p>
          <button className="w-full bg-green-700 text-white py-2 rounded-lg hover:bg-green-800 transition-colors text-sm font-medium opacity-75 cursor-not-allowed">
            Coming Soon
          </button>
        </div>
      </div>

      {/* Recent Members */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-8">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Users size={18} className="text-gray-600" />
          Family Members
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {persons.slice(0, 9).map((person) => (
            <button
              key={person.id}
              onClick={() => onSelectPerson(person)}
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-amber-50 transition-colors text-left border border-gray-100"
            >
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm ${
                person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
              }`}>
                {person.firstName[0]}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {person.firstName} {person.lastName}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {person.gotra} • {person.ancestralVillage}
                </p>
              </div>
              <span className={`w-2 h-2 rounded-full ${person.isLiving ? 'bg-green-400' : 'bg-gray-400'}`} />
            </button>
          ))}
        </div>
        {persons.length > 9 && (
          <button
            onClick={() => onNavigate('members')}
            className="mt-4 text-sm text-amber-700 hover:text-amber-800 font-medium"
          >
            View all {persons.length} members →
          </button>
        )}
      </div>

      {/* Household Distribution */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Home size={18} className="text-gray-600" />
          Household Distribution
        </h3>
        <div className="space-y-3">
          {households.map((household) => (
            <div key={household.id} className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
              <div className="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center">
                <Home size={16} className="text-amber-700" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-800">{household.name}</p>
                <p className="text-xs text-gray-500">{household.location}</p>
              </div>
              <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded-full font-medium">
                {household.memberIds.length} members
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sublabel, color }: {
  icon: React.ReactNode;
  label: string;
  value: number;
  sublabel: string;
  color: string;
}) {
  const bgColors: Record<string, string> = {
    blue: 'bg-blue-50 border-blue-100',
    green: 'bg-green-50 border-green-100',
    purple: 'bg-purple-50 border-purple-100',
    amber: 'bg-amber-50 border-amber-100',
  };

  return (
    <div className={`rounded-xl p-5 border ${bgColors[color]} shadow-sm`}>
      <div className="flex items-center gap-3 mb-2">
        {icon}
        <span className="text-sm text-gray-600 font-medium">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      <p className="text-xs text-gray-500 mt-1 truncate">{sublabel}</p>
    </div>
  );
}
