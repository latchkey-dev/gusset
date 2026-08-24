import { makeStatus } from '@demo/shared';
import { fetchStatus } from '@/lib/api';

export default function Page() {
  fetchStatus();
  makeStatus();
  return <main />;
}
