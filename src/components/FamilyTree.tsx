import { useState } from 'react';
import { Person, ViewMode } from '../types';
import { sampleHouseholds } from '../data/sampleData';
import { LayoutGrid, GitBranch, List, ZoomIn, ZoomOut } from 'lucide-react';

interface FamilyTreeProps {
  persons: Person[];
  rootPersonId: string;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  onSelectPerson: (person: Person) => void;
}

export default function FamilyTree({ persons, rootPersonId, viewMode, onViewModeChange, onSelectPerson }: FamilyTreeProps) {
  const [zoom, setZoom] = useState(1);
  const rootPerson = persons.find(p => p.id === rootPersonId);

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-800">Family Tree</h2>
          <span className="text-sm text-gray-500">— {rootPerson?.firstName} {rootPerson?.lastName}'s Lineage</span>
        </div>
        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => onViewModeChange('cluster')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'cluster' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <LayoutGrid size={14} /> Cluster
            </button>
            <button
              onClick={() => onViewModeChange('tree')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'tree' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <GitBranch size={14} /> Pedigree
            </button>
            <button
              onClick={() => onViewModeChange('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'list' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <List size={14} /> List
            </button>
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center gap-1 ml-4">
            <button
              onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600"
            >
              <ZoomOut size={16} />
            </button>
            <span className="text-xs text-gray-500 w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom(Math.min(2, zoom + 0.1))}
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600"
            >
              <ZoomIn size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-auto p-6 bg-gray-50">
        {viewMode === 'cluster' && (
          <ClusterView persons={persons} onSelectPerson={onSelectPerson} zoom={zoom} />
        )}
        {viewMode === 'tree' && (
          <PedigreeView persons={persons} rootPersonId={rootPersonId} onSelectPerson={onSelectPerson} zoom={zoom} />
        )}
        {viewMode === 'list' && (
          <ListView persons={persons} onSelectPerson={onSelectPerson} />
        )}
      </div>
    </div>
  );
}

function ClusterView({ persons, onSelectPerson, zoom }: { persons: Person[]; onSelectPerson: (p: Person) => void; zoom: number }) {
  return (
    <div className="space-y-8" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
      {/* Root Generation */}
      <div className="text-center mb-4">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Root Generation (1920s)</span>
      </div>
      <div className="flex justify-center mb-8">
        {persons.filter(p => !p.fatherId && !p.motherId && p.spouseIds.length > 0 && !p.isLiving).map(person => (
          <PersonNode key={person.id} person={person} onClick={() => onSelectPerson(person)} isRoot />
        ))}
      </div>

      {/* Households */}
      <div className="text-center mb-4">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Households / Joint Family Clusters</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {sampleHouseholds.map(household => {
          const members = household.memberIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];
          const head = members.find(p => p.id === household.headId);
          
          return (
            <div key={household.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-amber-50 to-orange-50 px-4 py-3 border-b border-amber-100">
                <h4 className="font-medium text-gray-800 text-sm">{household.name}</h4>
                <p className="text-xs text-gray-500">{household.location}</p>
              </div>
              <div className="p-4">
                <div className="flex flex-wrap gap-2">
                  {members.map(member => (
                    <button
                      key={member.id}
                      onClick={() => onSelectPerson(member)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all hover:shadow-md ${
                        member.id === household.headId
                          ? 'border-amber-300 bg-amber-50'
                          : 'border-gray-200 hover:border-amber-200'
                      }`}
                    >
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                        member.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                      }`}>
                        {member.firstName[0]}
                      </div>
                      <div className="text-left">
                        <p className="text-xs font-medium text-gray-800">{member.firstName}</p>
                        <p className="text-[10px] text-gray-500">{member.isLiving ? 'Living' : '✝'}</p>
                      </div>
                      {member.id === household.headId && (
                        <span className="text-[10px] bg-amber-200 text-amber-800 px-1.5 py-0.5 rounded">Head</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Connection Lines Legend */}
      <div className="bg-white rounded-xl p-4 border border-gray-200">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Legend</h4>
        <div className="flex flex-wrap gap-4 text-xs">
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-blue-500"></span> Male
          </span>
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-pink-500"></span> Female
          </span>
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-green-400"></span> Living
          </span>
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-gray-400"></span> Deceased
          </span>
          <span className="flex items-center gap-2">
            <span className="w-4 h-4 rounded border-2 border-amber-300 bg-amber-50"></span> Household Head
          </span>
        </div>
      </div>
    </div>
  );
}

function PedigreeView({ persons, rootPersonId, onSelectPerson, zoom }: { persons: Person[]; rootPersonId: string; onSelectPerson: (p: Person) => void; zoom: number }) {
  const root = persons.find(p => p.id === rootPersonId);
  if (!root) return null;

  const getChildren = (personId: string) => persons.filter(p => p.fatherId === personId || p.motherId === personId);
  const getSpouse = (person: Person) => person.spouseIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];

  const renderGeneration = (person: Person, depth: number = 0): React.ReactNode => {
    const children = getChildren(person.id);
    const spouse = getSpouse(person);

    return (
      <div key={person.id} className="flex flex-col items-center">
        <div className="flex items-center gap-2 mb-2">
          <button
            onClick={() => onSelectPerson(person)}
            className={`px-3 py-2 rounded-lg border-2 transition-all hover:shadow-lg ${
              person.gender === 'male' ? 'border-blue-300 bg-blue-50' : 'border-pink-300 bg-pink-50'
            }`}
          >
            <p className="text-xs font-medium text-gray-800">{person.firstName} {person.lastName}</p>
            <p className="text-[10px] text-gray-500">
              {person.birthDate?.split('-')[0]}{person.deathDate ? ` - ${person.deathDate.split('-')[0]}` : ' - present'}
            </p>
          </button>
          {spouse.map(s => (
            <div key={s.id} className="flex items-center">
              <span className="text-red-400 mx-1">♥</span>
              <button
                onClick={() => onSelectPerson(s)}
                className={`px-3 py-2 rounded-lg border-2 transition-all hover:shadow-lg ${
                  s.gender === 'male' ? 'border-blue-300 bg-blue-50' : 'border-pink-300 bg-pink-50'
                }`}
              >
                <p className="text-xs font-medium text-gray-800">{s.firstName} {s.lastName}</p>
                <p className="text-[10px] text-gray-500">
                  {s.birthDate?.split('-')[0]}{s.deathDate ? ` - ${s.deathDate.split('-')[0]}` : ' - present'}
                </p>
              </button>
            </div>
          ))}
        </div>
        {children.length > 0 && (
          <div className="flex flex-col items-center">
            <div className="w-px h-6 bg-gray-300"></div>
            <div className="flex gap-4">
              {children.map(child => renderGeneration(child, depth + 1))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="overflow-x-auto" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
      <div className="min-w-max p-8">
        <div className="flex justify-center">
          {renderGeneration(root)}
        </div>
      </div>
    </div>
  );
}

function ListView({ persons, onSelectPerson }: { persons: Person[]; onSelectPerson: (p: Person) => void }) {
  const generations = [
    { label: 'Generation 1 (Grandparents)', filter: (p: Person) => !p.fatherId && !p.motherId && p.childrenIds.length > 0 },
    { label: 'Generation 2 (Parents)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      return parent && !parent.fatherId;
    }},
    { label: 'Generation 3 (Current)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      if (!parent) return false;
      const grandparent = persons.find(pp => pp.childrenIds.includes(parent.id));
      return grandparent && !grandparent.fatherId;
    }},
    { label: 'Generation 4 (Children)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      if (!parent) return false;
      const grandparent = persons.find(pp => pp.childrenIds.includes(parent.id));
      if (!grandparent) return false;
      const greatGrandparent = persons.find(pp => pp.childrenIds.includes(grandparent.id));
      return !!greatGrandparent;
    }},
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {generations.map((gen, idx) => {
        const members = persons.filter(gen.filter);
        if (members.length === 0) return null;
        return (
          <div key={idx} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
              <h4 className="font-medium text-gray-700 text-sm">{gen.label}</h4>
            </div>
            <div className="divide-y divide-gray-100">
              {members.map(person => (
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
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">{person.firstName} {person.lastName}</p>
                    <p className="text-xs text-gray-500">{person.gotra} • {person.occupation}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500">{person.ancestralVillage}</p>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                      person.isLiving ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {person.isLiving ? 'Living' : 'Deceased'}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PersonNode({ person, onClick, isRoot }: { person: Person; onClick: () => void; isRoot?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center p-4 rounded-xl border-2 transition-all hover:shadow-lg ${
        isRoot ? 'border-amber-400 bg-amber-50 shadow-md' : 'border-gray-200 bg-white'
      }`}
    >
      <div className={`w-12 h-12 rounded-full flex items-center justify-center text-white font-bold mb-2 ${
        person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
      }`}>
        {person.firstName[0]}
      </div>
      <p className="text-sm font-medium text-gray-800">{person.firstName} {person.lastName}</p>
      <p className="text-xs text-gray-500">{person.birthDate?.split('-')[0]} - {person.deathDate?.split('-')[0] || 'present'}</p>
      {person.gotra && (
        <span className="mt-1 text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
          {person.gotra} Gotra
        </span>
      )}
    </button>
  );
}
