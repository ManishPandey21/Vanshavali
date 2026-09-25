import { useState } from 'react';
import { Page, Person, ViewMode } from './types';
import { samplePersons, sampleFamily, sampleHouseholds } from './data/sampleData';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import FamilyTree from './components/FamilyTree';
import MemberList from './components/MemberList';
import AddPerson from './components/AddPerson';
import PersonDetail from './components/PersonDetail';
import GotraView from './components/GotraView';
import SearchView from './components/SearchView';
import BiodataGenerator from './components/BiodataGenerator';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [persons, setPersons] = useState<Person[]>(samplePersons);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [biodataPerson, setBiodataPerson] = useState<Person | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('tree');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleSelectPerson = (person: Person) => {
    setSelectedPerson(person);
    setCurrentPage('tree');
  };

  const handleAddPerson = (person: Person) => {
    setPersons([...persons, person]);
    setCurrentPage('members');
  };

  const handleGenerateBiodata = (person: Person) => {
    setBiodataPerson(person);
    setCurrentPage('dashboard'); // Will show biodata view
  };

  const renderPage = () => {
    if (biodataPerson) {
      return (
        <BiodataGenerator
          person={biodataPerson}
          persons={persons}
          onBack={() => setBiodataPerson(null)}
        />
      );
    }

    if (selectedPerson && currentPage === 'tree') {
      return (
        <PersonDetail
          person={selectedPerson}
          persons={persons}
          onBack={() => setSelectedPerson(null)}
          onSelectPerson={handleSelectPerson}
          onGenerateBiodata={handleGenerateBiodata}
        />
      );
    }

    switch (currentPage) {
      case 'dashboard':
        return (
          <Dashboard
            family={sampleFamily}
            persons={persons}
            households={sampleHouseholds}
            onSelectPerson={handleSelectPerson}
            onNavigate={setCurrentPage}
            onGenerateBiodata={handleGenerateBiodata}
          />
        );
      case 'tree':
        return (
          <FamilyTree
            persons={persons}
            rootPersonId={sampleFamily.rootPersonId}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            onSelectPerson={handleSelectPerson}
          />
        );
      case 'members':
        return (
          <MemberList
            persons={persons}
            onSelectPerson={handleSelectPerson}
            onAddPerson={() => setCurrentPage('add')}
          />
        );
      case 'add':
        return (
          <AddPerson
            persons={persons}
            onAdd={handleAddPerson}
            onCancel={() => setCurrentPage('members')}
          />
        );
      case 'gotra':
        return <GotraView persons={persons} />;
      case 'search':
        return (
          <SearchView
            persons={persons}
            onSelectPerson={handleSelectPerson}
          />
        );
      default:
        return (
          <Dashboard
            family={sampleFamily}
            persons={persons}
            households={sampleHouseholds}
            onSelectPerson={handleSelectPerson}
            onNavigate={setCurrentPage}
            onGenerateBiodata={handleGenerateBiodata}
          />
        );
    }
  };

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar
        currentPage={currentPage}
        onNavigate={(page) => {
          setCurrentPage(page);
          setSelectedPerson(null);
        }}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />
      <main className={`flex-1 overflow-auto transition-all duration-300 ${sidebarOpen ? 'ml-0' : 'ml-0'}`}>
        {renderPage()}
      </main>
    </div>
  );
}

export default App;
