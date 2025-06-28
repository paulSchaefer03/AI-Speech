import { ApplicationShell } from "@/components/layout/ApplicationShell";
import { Providers } from "@/contexts/Providers";
import "@/styles/App.css";
//Eine App-Komponente, die die Hauptanwendung darstellt und die Anwendungsschale sowie die Kontext-Provider einbindet.
function App() {
  return (
    <div className="App">
      <Providers>
        <ApplicationShell />
      </Providers>
    </div>
  );
}

export default App;
