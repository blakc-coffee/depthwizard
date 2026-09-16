import { useEffect } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { Footer } from '../components/layout/Footer';
import { SiltUploadForm } from '../components/upload/SiltUploadForm';

export const SiltWorkspacePage = () => {
  useEffect(() => {
    document.title = 'DepthWizard | New River Silt Job';
  }, []);

  return (
    <AppShell footer={<Footer />}>
      <SiltUploadForm />
    </AppShell>
  );
};
