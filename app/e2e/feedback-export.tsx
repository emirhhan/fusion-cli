import { createRoot } from 'react-dom/client';
import '../src/theme/tokens.css';
import { FeedbackDialog } from '../src/feedback/FeedbackDialog';
const version = async () => '0.4.6';
createRoot(document.getElementById('root')!).render(<FeedbackDialog initial={{ tur: 'hata', mesaj: 'Yerel rapor kabulü', ayrinti: 'password=SENTINEL_DOWNLOAD' }} loadVersion={version} onClose={() => {}} />);
