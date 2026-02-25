import { getTopics } from "@/lib/observatory-api";
import { SearchPage } from "@/components/observatory/search-page";

export default async function Search() {
  let topics;
  try {
    topics = await getTopics();
  } catch {
    topics = null;
  }

  return <SearchPage topics={topics} />;
}
