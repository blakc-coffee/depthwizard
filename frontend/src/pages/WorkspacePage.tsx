import { useEffect } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { Footer } from '../components/layout/Footer';
import { UploadForm } from '../components/upload/UploadForm';

export const WorkspacePage = () => {
  useEffect(() => {
    document.title = 'DepthWizard | New Terrain Job';
  }, []);

  return (
    <AppShell footer={<Footer />}>
      <UploadForm />
    </AppShell>
  );
};
