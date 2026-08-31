import { Header } from './Header';

export const AppShell = ({
  children,
  footer,
}: {
  children: React.ReactNode;
  footer?: React.ReactNode;
}) => {
  return (
    <div className="min-h-screen bg-white text-[#36394a] font-sans flex flex-col antialiased w-full overflow-x-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-[#5e4cff] focus:text-white focus:rounded-[8px] focus:shadow-lg focus:outline-none"
      >
        Skip to main content
      </a>
      <main id="main-content" className="flex-1 w-full px-6 sm:px-10 lg:px-12 py-6 flex flex-col box-border overflow-x-hidden">
        <Header />
        {children}
      </main>
      {footer}
    </div>
  );
};
