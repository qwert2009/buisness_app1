

# # # n = int(input("Сколько любимых блюд ты хочешь ввести? "))

# # # dishes = []
# # # for i in range(n):
# # #     dish = input(f"Введи блюдо №{i + 1}: ")
# # #     dishes.append(dish)

# # # print("\nТвои любимые блюда:")
# # # for i, dish in enumerate(dishes, start=1):
# # #     print(f"{i}. {dish}")
# # dish_counter = int(input("how many dishes do you like? "))
# # dishes=[]
# # for i in range(dish_counter):
# #     dish=input(f"enter dish number {i+1}: ")
# #     dishes.append(dish)

# # print("your favorite dishes are: ")
# # for i in range(len(dishes)):
# #     print(f"{i+1}. {dishes[i]}")

# def get_all_indexes(items, value):
# 	return [i for i, item in enumerate(items) if item == value]

# some = ['a', 'b','a', 'c', 'd', 'e']
# name = input("enter a letter: ")
# print(get_all_indexes(some, name))

# import time as time

# time_start=time.time()
# some_list=['a', 'b','a', 'c', 'd', 'e']
# def get_all_indexes(spisok:list, search_data):
#     if search_data in spisok:
#         indexes=[]
#         count=spisok.count(search_data)
#         search_index=0
#         while count>0:
#             search_index=spisok.index(search_data, search_index)
#             indexes.append(search_index)
#             search_index+=1
#             count-=1
#         return indexes
#     return []
# print(get_all_indexes(some_list,'b'))
# end=time.time()
# print(end-time_start)
