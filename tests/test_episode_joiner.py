import unittest
from lola_episode_joiner import EpisodeLink, join_episode_links

class EpisodeJoinerTests(unittest.TestCase):
    def test_links_are_deduplicated_and_sorted(self):
        links=[EpisodeLink("a","VERIFIES","b"),EpisodeLink("a","VERIFIES","b"),EpisodeLink("c","CONTRADICTS","a")]
        out=join_episode_links(links)
        self.assertEqual(len(out),2)
        self.assertEqual(out[0],EpisodeLink("a","VERIFIES","b"))
    def test_invalid_relation_rejected(self):
        with self.assertRaises(ValueError): EpisodeLink("a","VOTES_FOR","b")

if __name__ == "__main__": unittest.main()
