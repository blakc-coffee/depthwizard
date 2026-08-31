import { Header } from './Header';

export const AppShell = ({
  children,
  footer,
}: {
  children: React.ReactNode;
  footer?: React.ReactNode;
}) => {
  return (
    <div className="min-h-screen bg-[#F6F4EC] text-gray-900 font-sans flex flex-col antialiased overflow-x-hidden w-full">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-purple-700 focus:text-white focus:rounded-md focus:shadow-lg focus:outline-none"
      >
        Skip to main content
      </a>
      <Header />
      <main id="main-content" className="flex-1 max-w-7xl w-full mx-auto p-3 sm:p-6 lg:p-8 overflow-x-hidden">
        {children}
      </main>
      {footer}
    </div>
  );
};
