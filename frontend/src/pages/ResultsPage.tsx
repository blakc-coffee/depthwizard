import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';

export const ResultsPage = () => {
  const { jobId } = useParams<{ jobId: string }>();

  useEffect(() => {
    document.title = 'DepthWizard | Terrain Results';
  }, []);

  return (
    <AppShell>
      <div className="bg-[#FDFCF8] border border-gray-200 rounded-xl p-6 sm:p-8 shadow-sm max-w-4xl mx-auto my-6 text-center">
        <h1 className="text-xl font-semibold text-gray-900 mb-2">Terrain Results</h1>
        <p className="text-sm font-mono text-gray-500 mb-4">Job ID: {jobId}</p>
        <p className="text-sm text-gray-600">Results workspace and 3D terrain viewer placeholder.</p>
      </div>
    </AppShell>
  );
};
