using System;
using System.Collections.Generic;

namespace GoldfishWalking.Map
{
    public sealed class MapGenerator
    {
        private const int MaxNodesPerFloor = 3;
        private const int BattleWeight = 4;
        private const int EliteWeight = 3;
        private const int RestWeight = 2;
        private const int ShopWeight = 1;

        public RunMap Generate(int seed, int roomCount)
        {
            return Generate(seed, 1, roomCount);
        }

        public RunMap Generate(int seed, int act, int roomCount)
        {
            int clampedAct = Math.Max(1, act);
            RunMap map = new RunMap { seed = seed, act = clampedAct };
            Random random = new Random(BuildMapSeed(seed, clampedAct));
            int clampedRoomCount = Math.Max(15, roomCount);
            List<List<MapNode>> floors = new List<List<MapNode>>();

            for (int floor = 0; floor < clampedRoomCount; floor++)
            {
                List<MapNode> previousFloor = floor > 0 ? floors[floor - 1] : null;
                List<MapNode> currentFloor = CreateFloor(floor, clampedRoomCount, previousFloor, random);
                floors.Add(currentFloor);
            }

            EnsureShopBeforeBoss(floors);
            ConnectFloors(floors);
            for (int floor = 0; floor < floors.Count; floor++)
                map.nodes.AddRange(floors[floor]);

            return map;
        }

        private static int BuildMapSeed(int seed, int act)
        {
            int mixed = unchecked((seed * 397) ^ (act * 1000003));
            return mixed & int.MaxValue;
        }

        private static List<MapNode> CreateFloor(int floor, int floorCount, List<MapNode> previousFloor, Random random)
        {
            int nodeCount = GetNodeCount(floor, floorCount, random);
            List<MapNode> floorNodes = new List<MapNode>(nodeCount);
            bool previousHasSpecial = HasSpecialNode(previousFloor);

            for (int lane = 0; lane < nodeCount; lane++)
            {
                MapNode node = new MapNode
                {
                    id = $"floor_{floor:D2}_node_{lane:D2}",
                    roomIndex = floor,
                    laneIndex = GetLaneIndex(lane, nodeCount),
                    nodeType = GetNodeType(floor, floorCount, previousHasSpecial, random)
                };

                floorNodes.Add(node);
            }

            return floorNodes;
        }

        private static int GetNodeCount(int floor, int floorCount, Random random)
        {
            if (floor < 2 || floor == floorCount - 1)
                return 1;

            return random.Next(1, MaxNodesPerFloor + 1);
        }

        private static int GetLaneIndex(int lane, int nodeCount)
        {
            if (nodeCount == 1)
                return 0;

            if (nodeCount == 2)
                return lane == 0 ? -1 : 1;

            return lane - 1;
        }

        private static MapNodeType GetNodeType(int floor, int floorCount, bool previousHasSpecial, Random random)
        {
            if (floor == floorCount - 1)
                return MapNodeType.Boss;

            if (floor < 2 || previousHasSpecial)
                return MapNodeType.NormalBattle;

            int totalWeight = BattleWeight + EliteWeight + ShopWeight + RestWeight;
            int roll = random.Next(0, totalWeight);
            if (roll < BattleWeight)
                return MapNodeType.NormalBattle;

            roll -= BattleWeight;
            if (roll < EliteWeight)
                return MapNodeType.EliteBattle;

            roll -= EliteWeight;
            if (roll < RestWeight)
                return MapNodeType.Rest;

            return MapNodeType.Shop;
        }

        private static void ConnectFloors(List<List<MapNode>> floors)
        {
            for (int floor = 0; floor + 1 < floors.Count; floor++)
            {
                List<MapNode> fromFloor = floors[floor];
                List<MapNode> toFloor = floors[floor + 1];

                for (int fromIndex = 0; fromIndex < fromFloor.Count; fromIndex++)
                {
                    int start;
                    int end;
                    GetContiguousTargetRange(fromFloor.Count, toFloor.Count, fromIndex, out start, out end);

                    for (int toIndex = start; toIndex <= end; toIndex++)
                        fromFloor[fromIndex].nextNodeIds.Add(toFloor[toIndex].id);
                }
            }
        }

        private static void GetContiguousTargetRange(int fromCount, int toCount, int fromIndex, out int start, out int end)
        {
            if (fromCount == 1)
            {
                start = 0;
                end = toCount - 1;
                return;
            }

            if (toCount == 1)
            {
                start = 0;
                end = 0;
                return;
            }

            if (fromCount == 2 && toCount == 2)
            {
                start = fromIndex;
                end = fromIndex == 0 ? 1 : 1;
                return;
            }

            if (fromCount == 2 && toCount == 3)
            {
                start = fromIndex;
                end = fromIndex + 1;
                return;
            }

            if (fromCount == 3 && toCount == 2)
            {
                start = fromIndex == 0 ? 0 : fromIndex == 1 ? 0 : 1;
                end = fromIndex == 0 ? 0 : 1;
                return;
            }

            start = fromIndex == 0 ? 0 : 1;
            end = fromIndex == 2 ? 2 : 1;
        }

        private static bool HasSpecialNode(List<MapNode> floor)
        {
            if (floor == null)
                return false;

            for (int i = 0; i < floor.Count; i++)
            {
                if (IsNonBattleSpecial(floor[i].nodeType))
                    return true;
            }

            return false;
        }

        private static bool IsNonBattleSpecial(MapNodeType nodeType)
        {
            return nodeType == MapNodeType.EliteBattle ||
                   nodeType == MapNodeType.Shop ||
                   nodeType == MapNodeType.Rest;
        }

        private static void EnsureShopBeforeBoss(List<List<MapNode>> floors)
        {
            if (floors.Count < 15)
                return;

            for (int floor = 0; floor <= 12; floor++)
            {
                for (int nodeIndex = 0; nodeIndex < floors[floor].Count; nodeIndex++)
                {
                    if (floors[floor][nodeIndex].nodeType == MapNodeType.Shop)
                        return;
                }
            }

            for (int nodeIndex = 0; nodeIndex < floors[12].Count; nodeIndex++)
            {
                if (IsNonBattleSpecial(floors[12][nodeIndex].nodeType))
                    floors[12][nodeIndex].nodeType = MapNodeType.NormalBattle;
            }

            floors[13].Clear();
            floors[13].Add(new MapNode
            {
                id = "floor_13_node_00",
                roomIndex = 13,
                laneIndex = 0,
                nodeType = MapNodeType.Shop
            });
        }
    }
}
