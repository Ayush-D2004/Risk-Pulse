import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import PortfolioOverview from './pages/PortfolioOverview';
import EventStress from './pages/EventStress';
import RiskAttribution from './pages/RiskAttribution';
import ScenarioComparison from './pages/ScenarioComparison';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<PortfolioOverview />} />
        <Route path="/events" element={<EventStress />} />
        <Route path="/attribution" element={<RiskAttribution />} />
        <Route path="/compare" element={<ScenarioComparison />} />
      </Routes>
    </Layout>
  );
}
